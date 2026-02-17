# lib/task_runner.py
from __future__ import annotations
import logging
import os
import tempfile
import shutil
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

from lib.models import Task, RepoConfig
from lib.git_ops import clone_repo, checkout_commit, get_commit_message, get_diff_stats, create_baseline_commit
from lib.docker_runner import run_in_docker
from lib.claude_runner import run_claude
from lib.prompt_builder import (
    build_prompt_from_commit_message,
    build_prompt_from_failing_test,
    build_prompt_from_issue,
    FLAT_PREAMBLE,
    INTENT_LAYER_PREAMBLE,
)
from lib.index_cache import IndexCache


# Progress callback type: (task_id, condition, step, message) -> None
ProgressCallback = Callable[[str, str, str, str], None]


class Condition(Enum):
    NONE = "none"
    FLAT_LLM = "flat_llm"
    INTENT_LAYER = "intent_layer"


@dataclass
class SkillGenerationMetrics:
    wall_clock_seconds: float
    input_tokens: int
    output_tokens: int
    cache_hit: bool = False
    files_created: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    task_id: str
    condition: Condition
    success: bool
    test_output: str
    wall_clock_seconds: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    lines_changed: int
    files_touched: list[str]
    skill_generation: SkillGenerationMetrics | None = None
    agents_files_read: list[str] | None = None
    error: str | None = None


class TaskRunner:
    def __init__(
        self,
        repo: RepoConfig,
        workspaces_dir: str,
        progress_callback: ProgressCallback | None = None,
        cache_dir: str = "workspaces/.index-cache",
        use_cache: bool = True
    ):
        self.repo = repo
        self.workspaces_dir = Path(workspaces_dir)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback
        self.index_cache = IndexCache(cache_dir) if use_cache else None

    def _progress(self, task_id: str, condition: str, step: str, message: str = ""):
        """Report progress if callback is set."""
        if self.progress_callback:
            self.progress_callback(task_id, condition, step, message)

    def _strip_context_files(self, workspace: str, strip_extra: list[str] | None = None) -> list[str]:
        """Remove AI context files from workspace. Returns list of removed paths.

        Uses the paper's exact universal pattern (agentbench.py:59-64):
          find . -type f ( -name "AGENTS.md" -o -name "CLAUDE.md" ) -delete
          rm -rf .github

        Per-repo extras (e.g., .cursorrules, .codex/) are handled via strip_extra.
        """
        removed = []
        workspace_path = Path(workspace)

        # Universal: remove all AGENTS.md and CLAUDE.md files
        for pattern in ["**/AGENTS.md", "**/CLAUDE.md"]:
            for match in workspace_path.glob(pattern):
                rel = str(match.relative_to(workspace_path))
                match.unlink()
                removed.append(rel)

        # Universal: remove .github directory
        github_dir = workspace_path / ".github"
        if github_dir.exists():
            shutil.rmtree(github_dir)
            removed.append(".github")

        # Per-repo extras
        if strip_extra:
            resolved_workspace = workspace_path.resolve()
            for extra in strip_extra:
                target = (workspace_path / extra).resolve()
                if not target.is_relative_to(resolved_workspace):
                    continue
                if target.is_file():
                    target.unlink()
                    removed.append(extra)
                elif target.is_dir():
                    shutil.rmtree(target)
                    removed.append(extra)

        return sorted(set(removed))

    def _check_or_generate_index(
        self,
        workspace: str,
        repo_url: str,
        commit: str,
        condition: str = "",
        model: str | None = None
    ) -> SkillGenerationMetrics:
        """Check cache or generate index. Returns metrics.

        Args:
            workspace: Path to workspace where index should be
            repo_url: Repository URL
            commit: Commit SHA

        Returns:
            SkillGenerationMetrics with cache_hit flag
        """
        # Check cache if enabled
        if self.index_cache:
            cache_entry = self.index_cache.lookup(repo_url, commit, condition)

            if cache_entry:
                # Cache hit: restore files
                start = time.time()
                self.index_cache.restore(cache_entry, workspace)
                elapsed = time.time() - start

                return SkillGenerationMetrics(
                    wall_clock_seconds=elapsed,
                    input_tokens=0,
                    output_tokens=0,
                    cache_hit=True,
                    files_created=cache_entry.agents_files
                )

        # Cache miss: generate index using the actual Intent Layer skill
        from lib.prompt_builder import build_skill_generation_prompt

        # Resolve plugin root (this repo) so scripts are findable
        plugin_root = str(Path(__file__).resolve().parent.parent.parent)

        # Write stderr to a log file so callers can tail for live progress
        log_dir = Path(self.workspaces_dir).parent / "logs"
        repo_slug = repo_url.split("/")[-1].replace(".git", "")
        stderr_log = log_dir / f"{repo_slug}-{commit[:8]}-skill_gen.log"

        prompt = build_skill_generation_prompt(plugin_root)
        result = run_claude(
            workspace, prompt, timeout=600, model=model,
            extra_env={"CLAUDE_PLUGIN_ROOT": plugin_root},
            stderr_log=str(stderr_log),
        )

        # Find generated AGENTS.md files
        agents_files = self._find_agents_files(workspace)

        # Save to cache if enabled
        if self.index_cache:
            self.index_cache.save(repo_url, commit, workspace, agents_files, condition)

        return SkillGenerationMetrics(
            wall_clock_seconds=result.wall_clock_seconds,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_hit=False,
            files_created=agents_files
        )

    def _generate_flat_context(
        self,
        workspace: str,
        repo_url: str,
        commit: str,
        model: str | None = None
    ) -> SkillGenerationMetrics:
        """Generate a flat CLAUDE.md using the paper's prompt. Returns metrics.

        After generation, dual-writes the content to both CLAUDE.md and AGENTS.md,
        matching the paper's behavior at init_planner.py:187-188.
        """
        # Check cache first
        if self.index_cache:
            cache_entry = self.index_cache.lookup(repo_url, commit, "flat_llm")
            if cache_entry:
                start = time.time()
                self.index_cache.restore(cache_entry, workspace)
                elapsed = time.time() - start
                return SkillGenerationMetrics(
                    wall_clock_seconds=elapsed,
                    input_tokens=0,
                    output_tokens=0,
                    cache_hit=True,
                    files_created=cache_entry.agents_files
                )

        from lib.prompt_builder import build_flat_generation_prompt

        # Write stderr to a log file so callers can tail for live progress
        log_dir = Path(self.workspaces_dir).parent / "logs"
        repo_slug = repo_url.split("/")[-1].replace(".git", "")
        stderr_log = log_dir / f"{repo_slug}-{commit[:8]}-flat_gen.log"

        prompt = build_flat_generation_prompt()
        result = run_claude(workspace, prompt, timeout=600, model=model,
                            stderr_log=str(stderr_log))

        # Dual-write: ensure both CLAUDE.md and AGENTS.md exist with same content
        workspace_path = Path(workspace)
        claude_md = workspace_path / "CLAUDE.md"
        agents_md = workspace_path / "AGENTS.md"

        # Claude should have created CLAUDE.md; copy to AGENTS.md
        if claude_md.exists() and not agents_md.exists():
            shutil.copy2(claude_md, agents_md)
        elif agents_md.exists() and not claude_md.exists():
            shutil.copy2(agents_md, claude_md)

        agents_files = self._find_agents_files(workspace)

        # Save to cache
        if self.index_cache:
            self.index_cache.save(repo_url, commit, workspace, agents_files, "flat_llm")

        return SkillGenerationMetrics(
            wall_clock_seconds=result.wall_clock_seconds,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_hit=False,
            files_created=agents_files
        )

    def run(self, task: Task, condition: Condition, model: str | None = None) -> TaskResult:
        """Execute a single task under the given condition."""
        cond_str = condition.value
        self._progress(task.id, cond_str, "setup", "creating workspace")
        workspace = self._setup_workspace(task, condition)

        try:
            # Setup: clone and checkout
            self._progress(task.id, cond_str, "clone", f"cloning {self.repo.url}")
            clone_repo(self.repo.url, workspace, shallow=False)
            self._progress(task.id, cond_str, "checkout", f"checking out {task.pre_fix_commit[:8]}")
            checkout_commit(workspace, task.pre_fix_commit)

            # Run docker setup
            for i, setup_cmd in enumerate(self.repo.docker.setup, 1):
                self._progress(task.id, cond_str, "docker_setup", f"[{i}/{len(self.repo.docker.setup)}] {setup_cmd}")
                run_in_docker(workspace, self.repo.docker.image, setup_cmd)

            # Strip context files (all conditions — paper's methodology)
            self._progress(task.id, cond_str, "strip", "removing existing context files")
            strip_extra = self.repo.strip_extra or None
            removed = self._strip_context_files(workspace, strip_extra)
            if removed:
                self._progress(task.id, cond_str, "strip_done", f"removed {len(removed)} file(s)")

            # Generate context based on condition
            skill_metrics = None

            if condition == Condition.INTENT_LAYER:
                log_dir = Path(self.workspaces_dir).parent / "logs"
                repo_slug = self.repo.url.split("/")[-1].replace(".git", "")
                skill_log = log_dir / f"{repo_slug}-{task.pre_fix_commit[:8]}-skill_gen.log"
                self._progress(task.id, cond_str, "skill_gen", f"checking cache or generating Intent Layer... (tail -f {skill_log})")
                skill_metrics = self._check_or_generate_index(
                    workspace=workspace,
                    repo_url=self.repo.url,
                    commit=task.pre_fix_commit,
                    condition=condition.value,
                    model=model
                )
                cache_status = "restored from cache" if skill_metrics.cache_hit else "generated"
                self._progress(task.id, cond_str, "skill_gen_done", f"{cache_status} {len(skill_metrics.files_created)} file(s) in {skill_metrics.wall_clock_seconds:.1f}s")

            elif condition == Condition.FLAT_LLM:
                log_dir = Path(self.workspaces_dir).parent / "logs"
                repo_slug = self.repo.url.split("/")[-1].replace(".git", "")
                flat_log = log_dir / f"{repo_slug}-{task.pre_fix_commit[:8]}-flat_gen.log"
                self._progress(task.id, cond_str, "flat_gen", f"checking cache or generating flat CLAUDE.md... (tail -f {flat_log})")
                skill_metrics = self._generate_flat_context(
                    workspace=workspace,
                    repo_url=self.repo.url,
                    commit=task.pre_fix_commit,
                    model=model
                )
                cache_status = "restored from cache" if skill_metrics.cache_hit else "generated"
                self._progress(task.id, cond_str, "flat_gen_done", f"{cache_status} {len(skill_metrics.files_created)} file(s) in {skill_metrics.wall_clock_seconds:.1f}s")

            # NONE: no generation, stripping already happened

            # Baseline commit: snapshot workspace state so diff stats
            # only measure changes made by Claude, not by the harness
            create_baseline_commit(workspace)

            # Build prompt with condition-appropriate preamble
            self._progress(task.id, cond_str, "prompt", "building prompt")
            prompt = self._build_prompt(task, workspace, condition)

            # Run Claude on the task
            log_dir = Path(self.workspaces_dir).parent / "logs"
            repo_slug = self.repo.url.split("/")[-1].replace(".git", "")
            fix_log = log_dir / f"{repo_slug}-{task.pre_fix_commit[:8]}-{cond_str}-fix.log"
            self._progress(task.id, cond_str, "claude", f"running Claude to fix the bug... (tail -f {fix_log})")
            claude_result = run_claude(workspace, prompt, model=model,
                                       stderr_log=str(fix_log))
            self._progress(task.id, cond_str, "claude_done", f"completed in {claude_result.wall_clock_seconds:.1f}s, {claude_result.tool_calls} tool calls")

            # Run tests (chain setup commands so pip installs persist in same container)
            test_cmd = self.repo.docker.test_command
            if self.repo.docker.setup:
                setup_chain = " && ".join(self.repo.docker.setup)
                test_cmd = f"{setup_chain} && {test_cmd}"
            self._progress(task.id, cond_str, "test", f"running tests: {self.repo.docker.test_command}")
            test_result = run_in_docker(
                workspace,
                self.repo.docker.image,
                test_cmd,
                timeout=300
            )
            test_status = "PASSED" if test_result.exit_code == 0 else "FAILED"
            self._progress(task.id, cond_str, "test_done", f"tests {test_status}")

            # Get diff stats
            self._progress(task.id, cond_str, "diff", "collecting diff stats")
            diff_stats = get_diff_stats(workspace)

            # Extract which AGENTS.md files were read during the fix
            agents_files_read = self._extract_agents_files_read(
                claude_result.stdout, workspace
            ) if condition != Condition.NONE else None

            return TaskResult(
                task_id=task.id,
                condition=condition,
                success=test_result.exit_code == 0,
                test_output=test_result.stdout + test_result.stderr,
                wall_clock_seconds=claude_result.wall_clock_seconds,
                input_tokens=claude_result.input_tokens,
                output_tokens=claude_result.output_tokens,
                tool_calls=claude_result.tool_calls,
                lines_changed=diff_stats.lines_changed,
                files_touched=diff_stats.files,
                skill_generation=skill_metrics,
                agents_files_read=agents_files_read
            )
        except Exception as e:
            logger.error("Infrastructure error in task %s (%s): %s", task.id, cond_str, e, exc_info=True)
            return TaskResult(
                task_id=task.id,
                condition=condition,
                success=False,
                test_output="",
                wall_clock_seconds=0,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                lines_changed=0,
                files_touched=[],
                error=f"[infrastructure] {e}"
            )

    def _setup_workspace(self, task: Task, condition: Condition) -> str:
        """Create workspace directory for this run."""
        repo_name = self.repo.url.split("/")[-1].replace(".git", "")
        workspace_name = f"{repo_name}-{task.pre_fix_commit[:8]}-{condition.value}"
        workspace = self.workspaces_dir / workspace_name

        # Clean if exists
        if workspace.exists():
            shutil.rmtree(workspace)

        return str(workspace)

    def _build_prompt(self, task: Task, workspace: str, condition: Condition) -> str:
        """Build the appropriate prompt based on task config."""
        preamble = {
            Condition.NONE: None,
            Condition.FLAT_LLM: FLAT_PREAMBLE,
            Condition.INTENT_LAYER: INTENT_LAYER_PREAMBLE,
        }[condition]

        if task.prompt_source == "commit_message":
            message = get_commit_message(workspace, task.fix_commit)
            return build_prompt_from_commit_message(message, preamble=preamble)

        elif task.prompt_source == "failing_test":
            # Run the test to get failure output
            test_cmd = self.repo.docker.test_command
            if task.test_pattern:
                test_cmd = f"{test_cmd} -k '{task.test_pattern}'"

            # Chain setup so pip installs are available
            if self.repo.docker.setup:
                setup_chain = " && ".join(self.repo.docker.setup)
                test_cmd = f"{setup_chain} && {test_cmd}"

            result = run_in_docker(
                workspace,
                self.repo.docker.image,
                test_cmd,
                timeout=120
            )
            return build_prompt_from_failing_test(
                result.stdout + result.stderr, preamble=preamble
            )

        elif task.prompt_source == "issue":
            # TODO: Implement GitHub issue fetching
            raise NotImplementedError("Issue-based prompts not yet implemented")

        else:
            raise ValueError(f"Unknown prompt_source: {task.prompt_source}")

    def _find_agents_files(self, workspace: str) -> list[str]:
        """Find all AGENTS.md and CLAUDE.md files in workspace."""
        import glob
        workspace_path = Path(workspace)
        files = []
        for pattern in ["CLAUDE.md", "**/AGENTS.md"]:
            for match in workspace_path.glob(pattern):
                # Return path relative to workspace
                files.append(str(match.relative_to(workspace_path)))
        return sorted(files)

    def _extract_agents_files_read(self, claude_output: str, workspace: str) -> list[str]:
        """Extract which AGENTS.md/CLAUDE.md files Claude read from JSON output.

        Handles both output formats:
        - List of messages (array at top level)
        - Dict with "messages" key
        """
        import json
        import re

        files_read = set()
        try:
            data = json.loads(claude_output)

            # Determine messages list based on output format
            if isinstance(data, list):
                messages = data
            elif isinstance(data, dict):
                messages = data.get("messages", [])
            else:
                messages = []

            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                if block.get("name") == "Read":
                                    inp = block.get("input", {})
                                    file_path = inp.get("file_path", "") if isinstance(inp, dict) else ""
                                    # Check if it's an AGENTS.md or CLAUDE.md file
                                    if re.search(r"(AGENTS|CLAUDE)\.md$", file_path):
                                        # Make relative to workspace
                                        if file_path.startswith(workspace):
                                            file_path = file_path[len(workspace):].lstrip("/")
                                        files_read.add(file_path)
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            pass

        return sorted(files_read)
