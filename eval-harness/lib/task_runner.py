# lib/task_runner.py
from __future__ import annotations
import json
import logging
import os
import re
import subprocess
import tempfile
import shutil
import sys
import threading
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

# Pre-validation timeout: Docker setup + test run must complete within this.
# 120s was too tight for repos with slow test setup (e.g., test_pagination.py
# under parallel Docker load). 180s gives headroom without masking real issues.
PRE_VALIDATION_TIMEOUT = 180

# Post-test timeout: running tests after Claude's fix. Should be comparable
# to pre-validation — if tests don't finish in this window, they're broken.
POST_TEST_TIMEOUT = 180


class PreValidationCache:
    """Thread-safe cache for pre-validation results across conditions.

    Pre-validation (Docker test run) produces identical results for all
    conditions of the same task — same commit, same code, same test.
    This cache ensures we only run Docker once per task, not once per
    (task, condition) pair.  For 8 tasks × 3 conditions, this eliminates
    16 redundant Docker runs (~30-60s each).

    Thread safety: when two conditions for the same task start concurrently,
    the first thread runs Docker while the second waits on an Event.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._results: dict[str, str | None] = {}
        self._in_progress: dict[str, threading.Event] = {}
        self._errors: dict[str, BaseException] = {}

    def get_or_compute(self, key: str, fn: Callable[[], str | None]) -> str | None:
        """Return cached result or compute it. Deduplicates concurrent calls."""
        with self._lock:
            if key in self._results:
                return self._results[key]
            if key in self._errors:
                orig = self._errors[key]
                raise type(orig)(str(orig))
            if key in self._in_progress:
                event = self._in_progress[key]
                is_first = False
            else:
                event = threading.Event()
                self._in_progress[key] = event
                is_first = True

        if not is_first:
            # Wait for the first caller to finish
            event.wait(timeout=PRE_VALIDATION_TIMEOUT + 60)
            with self._lock:
                if key in self._errors:
                    orig = self._errors[key]
                    raise type(orig)(str(orig))
                return self._results.get(key)

        # First caller — run the computation
        try:
            result = fn()
            with self._lock:
                self._results[key] = result
            return result
        except BaseException as e:
            with self._lock:
                self._errors[key] = e
            raise
        finally:
            event.set()


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
    exit_code: int | None = None
    is_timeout: bool = False


class PreValidationError(Exception):
    """Raised when a task fails pre-validation checks."""
    pass


class SkillGenerationError(Exception):
    """Raised when skill generation fails (timeout or empty output)."""
    pass


class TaskRunner:
    def __init__(
        self,
        repo: RepoConfig,
        workspaces_dir: str,
        progress_callback: ProgressCallback | None = None,
        cache_dir: str = "workspaces/.index-cache",
        use_cache: bool = True,
        reference_clone: str | None = None,
        pre_val_cache: PreValidationCache | None = None,
    ):
        self.repo = repo
        self.workspaces_dir = Path(workspaces_dir)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback
        self.index_cache = IndexCache(cache_dir) if use_cache else None
        self.reference_clone = reference_clone
        self.pre_val_cache = pre_val_cache

    def _progress(self, task_id: str, condition: str, step: str, message: str = ""):
        """Report progress if callback is set."""
        if self.progress_callback:
            self.progress_callback(task_id, condition, step, message)

    def _pre_validate(self, task: Task, workspace: str) -> str | None:
        """Validate that a task is runnable before spending API tokens.

        Checks:
        1. Docker setup commands succeed (deps install correctly)
        2. For failing_test tasks: the target test actually fails at pre_fix_commit
        3. Context files were fully stripped (no stale AGENTS.md/CLAUDE.md)

        Returns the test output (stdout+stderr) for failing_test tasks so it
        can be reused for prompt building, avoiding a redundant Docker run.
        Returns None for non-test tasks (commit_message smoke tests).

        Raises PreValidationError with a descriptive message on failure.
        """
        test_output = None

        # 1. Verify test infrastructure
        if task.prompt_source != "failing_test" and not task.test_file:
            # commit_message tasks without test_file: just verify setup works.
            # Running the full suite here is too slow and risks timeouts.
            if self.repo.docker.setup:
                setup_chain = " && ".join(self.repo.docker.setup)
                smoke_cmd = f"{setup_chain} && python --version"
            else:
                smoke_cmd = "python --version"

            result = run_in_docker(
                workspace, self.repo.docker.image, smoke_cmd, timeout=PRE_VALIDATION_TIMEOUT
            )
            if result.timed_out:
                raise PreValidationError(
                    "Docker setup timed out during pre-validation."
                )
            if result.exit_code != 0:
                raise PreValidationError(
                    f"Docker setup failed (exit {result.exit_code})."
                )
        else:
            # Run specific test file or full suite
            test_cmd = self.repo.docker.test_command
            if task.test_file:
                test_cmd = f"{test_cmd} {task.test_file}"
            if task.test_pattern:
                test_cmd = f"{test_cmd} -k '{task.test_pattern}'"

            if self.repo.docker.setup:
                setup_chain = " && ".join(self.repo.docker.setup)
                test_cmd = f"{setup_chain} && {test_cmd}"

            result = run_in_docker(
                workspace, self.repo.docker.image, test_cmd, timeout=PRE_VALIDATION_TIMEOUT
            )

            # 2. The test MUST fail at pre_fix_commit (that's the whole point)
            if task.prompt_source == "failing_test" and result.exit_code == 0:
                raise PreValidationError(
                    f"Test already passes at pre_fix_commit {task.pre_fix_commit[:8]}. "
                    f"This task is not a valid failing-test scenario."
                )

            if result.timed_out:
                raise PreValidationError(
                    "Test command timed out during pre-validation. "
                    "Docker setup or test infrastructure may be broken."
                )

            # Save test output for prompt building (avoids redundant Docker run)
            test_output = result.stdout + result.stderr

        # 3. Verify no residual context files (strip worked)
        workspace_path = Path(workspace)
        residual = []
        for pattern in ["**/AGENTS.md", "**/CLAUDE.md"]:
            for match in workspace_path.glob(pattern):
                residual.append(str(match.relative_to(workspace_path)))
        if residual:
            raise PreValidationError(
                f"Context files remain after stripping: {residual}. "
                f"Check strip_extra config."
            )

        return test_output

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

    def _inject_test_from_fix(self, task: Task, workspace: str) -> bool:
        """Inject test file from fix_commit into pre_fix workspace.

        Many repos add test functions alongside code fixes. The test file may
        exist at pre_fix_commit but without the functions that reproduce the bug.
        Injecting the fix_commit version creates a valid failing-test scenario:
        the new test functions fail because the code hasn't been fixed yet.

        Returns True if injection was performed.
        """
        if not task.test_file or not task.fix_commit:
            return False

        try:
            result = subprocess.run(
                ["git", "show", f"{task.fix_commit}:{task.test_file}"],
                capture_output=True, text=True, check=True,
                cwd=workspace
            )
            test_path = Path(workspace) / task.test_file
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(result.stdout)
            return True
        except subprocess.CalledProcessError:
            return False

    def _check_or_generate_index(
        self,
        workspace: str,
        repo_url: str,
        commit: str,
        condition: str = "",
        model: str | None = None,
        timeout: int = 600,
        repo_level: bool = False
    ) -> SkillGenerationMetrics:
        """Check cache or generate index. Returns metrics.

        Args:
            workspace: Path to workspace where index should be
            repo_url: Repository URL
            commit: Commit SHA
            timeout: Generation timeout in seconds (default 600)
            repo_level: If True, use repo-level cache key (no commit)

        Returns:
            SkillGenerationMetrics with cache_hit flag
        """
        # Check cache if enabled — try repo-level first, then per-commit
        if self.index_cache:
            cache_entry = self.index_cache.lookup_repo(repo_url, condition)
            if not cache_entry:
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
            workspace, prompt, timeout=timeout, model=model,
            extra_env={"CLAUDE_PLUGIN_ROOT": plugin_root},
            stderr_log=str(stderr_log),
        )

        # Find generated AGENTS.md files
        agents_files = self._find_agents_files(workspace)

        # Save to cache if enabled
        if self.index_cache:
            self.index_cache.save(repo_url, commit, workspace, agents_files, condition, repo_level=repo_level)

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
        model: str | None = None,
        timeout: int = 600,
        repo_level: bool = False
    ) -> SkillGenerationMetrics:
        """Generate a flat CLAUDE.md using the paper's prompt. Returns metrics.

        After generation, dual-writes the content to both CLAUDE.md and AGENTS.md,
        matching the paper's behavior at init_planner.py:187-188.
        """
        # Check cache — try repo-level first, then per-commit
        if self.index_cache:
            cache_entry = self.index_cache.lookup_repo(repo_url, "flat_llm")
            if not cache_entry:
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
        result = run_claude(workspace, prompt, timeout=timeout, model=model,
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
            self.index_cache.save(repo_url, commit, workspace, agents_files, "flat_llm", repo_level=repo_level)

        return SkillGenerationMetrics(
            wall_clock_seconds=result.wall_clock_seconds,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_hit=False,
            files_created=agents_files
        )

    def warm_cache(
        self,
        repo_url: str,
        condition: Condition,
        model: str | None = None,
        timeout: int = 900
    ) -> SkillGenerationMetrics | None:
        """Pre-generate context files once per repo+condition into the cache.

        Context files (AGENTS.md, CLAUDE.md) describe repo structure and
        conventions, which are stable across nearby commits. So we generate
        from the default branch once and reuse for all tasks in the repo.

        Called once per unique (repo, condition) before the task loop.
        Subsequent task runs restore from the repo-level cache entry.
        Uses a longer timeout (default 900s) since this only runs once.

        Returns SkillGenerationMetrics if generation was needed, None for the
        'none' condition (which has no context files to generate).
        """
        if condition == Condition.NONE:
            return None

        cond_key = condition.value

        # Already cached at repo level? Nothing to do.
        if self.index_cache:
            if self.index_cache.lookup_repo(repo_url, cond_key):
                logger.info("Cache hit for %s (%s), skipping warm", repo_url, condition.value)
                return None

        # Clone default branch for generation (structure is commit-agnostic)
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        workspace_name = f"{repo_name}-{condition.value}-warmup"
        workspace = str(self.workspaces_dir / workspace_name)

        if Path(workspace).exists():
            shutil.rmtree(workspace)

        try:
            if self.reference_clone:
                self._progress("warmup", condition.value, "clone", "local clone from reference")
            else:
                self._progress("warmup", condition.value, "clone", f"cloning {repo_url}")
            clone_repo(repo_url, workspace, shallow=False, reference=self.reference_clone)
            # Use default branch HEAD — no checkout_commit needed

            self._progress("warmup", condition.value, "strip", "removing existing context files")
            strip_extra = self.repo.strip_extra or None
            self._strip_context_files(workspace, strip_extra)

            self._progress("warmup", condition.value, "generate", f"generating {condition.value} context (timeout={timeout}s)")
            if condition == Condition.INTENT_LAYER:
                metrics = self._check_or_generate_index(
                    workspace=workspace,
                    repo_url=repo_url,
                    commit="latest",
                    condition=cond_key,
                    model=model,
                    timeout=timeout,
                    repo_level=True
                )
            else:  # FLAT_LLM
                metrics = self._generate_flat_context(
                    workspace=workspace,
                    repo_url=repo_url,
                    commit="latest",
                    model=model,
                    timeout=timeout,
                    repo_level=True
                )

            if not metrics.cache_hit and not metrics.files_created:
                raise SkillGenerationError(
                    f"{condition.value} generation produced no files "
                    f"(took {metrics.wall_clock_seconds:.0f}s). "
                    f"Likely timed out or failed silently."
                )

            status = "cached" if metrics.cache_hit else f"generated {len(metrics.files_created)} file(s)"
            self._progress("warmup", condition.value, "done", f"{status} in {metrics.wall_clock_seconds:.1f}s")
            return metrics

        finally:
            # Clean up warmup workspace — the files are in the cache now
            if Path(workspace).exists():
                shutil.rmtree(workspace)

    def run(self, task: Task, condition: Condition, model: str | None = None, rep: int = 0) -> TaskResult:
        """Execute a single task under the given condition."""
        cond_str = condition.value
        self._progress(task.id, cond_str, "setup", "creating workspace")
        workspace = self._setup_workspace(task, condition, rep=rep)

        try:
            # Setup: clone and checkout
            if self.reference_clone:
                self._progress(task.id, cond_str, "clone", f"local clone from reference")
            else:
                self._progress(task.id, cond_str, "clone", f"cloning {self.repo.url}")
            clone_repo(self.repo.url, workspace, shallow=False, reference=self.reference_clone)
            self._progress(task.id, cond_str, "checkout", f"checking out {task.pre_fix_commit[:8]}")
            checkout_commit(workspace, task.pre_fix_commit)

            # Strip context files (all conditions — paper's methodology)
            self._progress(task.id, cond_str, "strip", "removing existing context files")
            strip_extra = self.repo.strip_extra or None
            removed = self._strip_context_files(workspace, strip_extra)
            if removed:
                self._progress(task.id, cond_str, "strip_done", f"removed {len(removed)} file(s)")

            # Inject test file from fix commit for failing_test tasks.
            # Many repos add test functions alongside code fixes, so the test
            # file at pre_fix_commit passes (the bug-reproducing tests haven't
            # been written yet). Injecting fix_commit's version gives us
            # those functions, which fail because the code hasn't been fixed.
            if task.prompt_source == "failing_test" and task.test_file:
                if self._inject_test_from_fix(task, workspace):
                    self._progress(task.id, cond_str, "inject_test",
                                   f"injected {task.test_file} from fix commit")

            # Pre-validate: confirm test infra works and test actually fails.
            # Pre-validation is identical across conditions for the same task
            # (same commit, same code, same test), so we cache the result.
            if self.pre_val_cache is not None:
                self._progress(task.id, cond_str, "pre_validate", "checking pre-validation cache")
                pre_validate_output = self.pre_val_cache.get_or_compute(
                    task.id, lambda: self._pre_validate(task, workspace)
                )
            else:
                self._progress(task.id, cond_str, "pre_validate", "verifying test fails at pre_fix_commit")
                pre_validate_output = self._pre_validate(task, workspace)
            self._progress(task.id, cond_str, "pre_validate_done", "pre-validation passed")

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
                if not skill_metrics.cache_hit and not skill_metrics.files_created:
                    raise SkillGenerationError(
                        f"Intent Layer generation produced no files "
                        f"(took {skill_metrics.wall_clock_seconds:.0f}s). "
                        f"Likely timed out or failed silently."
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
                if not skill_metrics.cache_hit and not skill_metrics.files_created:
                    raise SkillGenerationError(
                        f"Flat CLAUDE.md generation produced no files "
                        f"(took {skill_metrics.wall_clock_seconds:.0f}s). "
                        f"Likely timed out or failed silently."
                    )
                cache_status = "restored from cache" if skill_metrics.cache_hit else "generated"
                self._progress(task.id, cond_str, "flat_gen_done", f"{cache_status} {len(skill_metrics.files_created)} file(s) in {skill_metrics.wall_clock_seconds:.1f}s")

            # NONE: no generation, stripping already happened

            # Baseline commit: snapshot workspace state so diff stats
            # only measure changes made by Claude, not by the harness
            create_baseline_commit(workspace)

            # Build prompt with condition-appropriate preamble
            self._progress(task.id, cond_str, "prompt", "building prompt")
            prompt = self._build_prompt(task, workspace, condition, cached_test_output=pre_validate_output)

            # Run Claude on the task
            log_dir = Path(self.workspaces_dir).parent / "logs"
            repo_slug = self.repo.url.split("/")[-1].replace(".git", "")
            fix_log = log_dir / f"{repo_slug}-{task.pre_fix_commit[:8]}-{cond_str}-fix.log"
            self._progress(task.id, cond_str, "claude", f"running Claude to fix the bug... (tail -f {fix_log})")
            claude_result = run_claude(workspace, prompt, model=model,
                                       stderr_log=str(fix_log))
            self._progress(task.id, cond_str, "claude_done", f"completed in {claude_result.wall_clock_seconds:.1f}s, {claude_result.tool_calls} tool calls")

            # Detect empty runs: Claude returned without doing any work
            if (claude_result.tool_calls == 0
                    and claude_result.input_tokens == 0
                    and claude_result.output_tokens == 0
                    and not claude_result.timed_out):
                # Include stderr for diagnosis — often reveals why CLI failed
                stderr_snippet = claude_result.stderr.strip()[:200] if claude_result.stderr else ""
                stderr_info = f", stderr={stderr_snippet!r}" if stderr_snippet else ""
                prompt_size = len(prompt.encode("utf-8"))
                return TaskResult(
                    task_id=task.id,
                    condition=condition,
                    success=False,
                    test_output="",
                    wall_clock_seconds=claude_result.wall_clock_seconds,
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls=0,
                    lines_changed=0,
                    files_touched=[],
                    error=(
                        f"[empty-run] Claude produced no output "
                        f"(exit_code={claude_result.exit_code}, "
                        f"{claude_result.wall_clock_seconds:.1f}s, "
                        f"prompt_bytes={prompt_size}{stderr_info})"
                    ),
                    exit_code=claude_result.exit_code,
                )

            # Detect timeout: Claude ran out of time
            if claude_result.timed_out:
                return TaskResult(
                    task_id=task.id,
                    condition=condition,
                    success=False,
                    test_output="",
                    wall_clock_seconds=claude_result.wall_clock_seconds,
                    input_tokens=claude_result.input_tokens,
                    output_tokens=claude_result.output_tokens,
                    tool_calls=claude_result.tool_calls,
                    lines_changed=0,
                    files_touched=[],
                    error=(
                        f"[timeout] Claude timed out after "
                        f"{claude_result.wall_clock_seconds:.1f}s"
                    ),
                    exit_code=claude_result.exit_code,
                    is_timeout=True,
                )

            # Run tests — use targeted test file when available (~150s → ~15s)
            test_cmd = self.repo.docker.test_command
            if task.test_file:
                test_cmd = f"{test_cmd} {task.test_file}"
            if task.test_pattern:
                test_cmd = f"{test_cmd} -k '{task.test_pattern}'"
            if self.repo.docker.setup:
                setup_chain = " && ".join(self.repo.docker.setup)
                test_cmd = f"{setup_chain} && {test_cmd}"
            self._progress(task.id, cond_str, "test", f"running tests: {test_cmd}")
            test_result = run_in_docker(
                workspace,
                self.repo.docker.image,
                test_cmd,
                timeout=POST_TEST_TIMEOUT
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
                agents_files_read=agents_files_read,
                exit_code=claude_result.exit_code,
            )
        except PreValidationError as e:
            logger.warning("Pre-validation failed for %s (%s): %s", task.id, cond_str, e)
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
                error=f"[pre-validation] {e}"
            )
        except SkillGenerationError as e:
            logger.warning("Skill generation failed for %s (%s): %s", task.id, cond_str, e)
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
                error=f"[skill-generation] {e}"
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

    def _setup_workspace(self, task: Task, condition: Condition, rep: int = 0) -> str:
        """Create workspace directory for this run.

        Includes rep index in the path to avoid collisions when running
        multiple repetitions in parallel.
        """
        repo_name = self.repo.url.split("/")[-1].replace(".git", "")
        # Include task ID hash to avoid collisions when tasks share a commit
        task_hash = format(hash(task.id) % 0xFFFF, '04x')
        workspace_name = f"{repo_name}-{task.pre_fix_commit[:8]}-{task_hash}-{condition.value}-r{rep}"
        workspace = self.workspaces_dir / workspace_name

        # Clean if exists
        if workspace.exists():
            shutil.rmtree(workspace)

        return str(workspace)

    def _build_prompt(self, task: Task, workspace: str, condition: Condition, cached_test_output: str | None = None) -> str:
        """Build the appropriate prompt based on task config.

        Args:
            cached_test_output: Pre-validation test output to reuse for
                failing_test prompts, avoiding a redundant Docker run.
        """
        preamble = {
            Condition.NONE: None,
            Condition.FLAT_LLM: FLAT_PREAMBLE,
            Condition.INTENT_LAYER: INTENT_LAYER_PREAMBLE,
        }[condition]

        if task.prompt_source == "commit_message":
            message = get_commit_message(workspace, task.fix_commit)
            return build_prompt_from_commit_message(message, preamble=preamble)

        elif task.prompt_source == "failing_test":
            # Reuse pre-validation output if available (saves ~12s Docker run)
            if cached_test_output:
                return build_prompt_from_failing_test(
                    cached_test_output, preamble=preamble
                )

            # Fallback: run Docker to get test output
            if task.test_file:
                test_cmd = f"{self.repo.docker.test_command} {task.test_file}"
            else:
                test_cmd = self.repo.docker.test_command
            if task.test_pattern:
                test_cmd = f"{test_cmd} -k '{task.test_pattern}'"

            if self.repo.docker.setup:
                setup_chain = " && ".join(self.repo.docker.setup)
                test_cmd = f"{setup_chain} && {test_cmd}"

            result = run_in_docker(
                workspace,
                self.repo.docker.image,
                test_cmd,
                timeout=PRE_VALIDATION_TIMEOUT
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
