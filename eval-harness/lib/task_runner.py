# lib/task_runner.py
from __future__ import annotations
import os
import tempfile
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from lib.models import Task, RepoConfig
from lib.git_ops import clone_repo, checkout_commit, get_commit_message, get_diff_stats
from lib.docker_runner import run_in_docker
from lib.claude_runner import run_claude
from lib.prompt_builder import (
    build_prompt_from_commit_message,
    build_prompt_from_failing_test,
    build_prompt_from_issue
)


# Progress callback type: (task_id, condition, step, message) -> None
ProgressCallback = Callable[[str, str, str, str], None]


class Condition(Enum):
    WITH_SKILL = "with_skill"
    WITHOUT_SKILL = "without_skill"


SKILL_GENERATION_PROMPT = """Create an Intent Layer for this codebase to help with bug fixing.

1. Run scripts/detect_state.sh to check current state
2. Run scripts/analyze_structure.sh to find semantic boundaries
3. Create a root CLAUDE.md with:
   - Entry points for key functionality
   - Architecture overview (components, data flow)
   - Pitfalls extracted from git history (use git-history sub-skill)
   - Contracts that must be maintained
4. Create AGENTS.md child nodes for directories with distinct responsibilities

Focus on information that would help someone unfamiliar with the codebase navigate and fix bugs safely."""


@dataclass
class SkillGenerationMetrics:
    wall_clock_seconds: float
    input_tokens: int
    output_tokens: int
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
    def __init__(self, repo: RepoConfig, workspaces_dir: str, progress_callback: ProgressCallback | None = None):
        self.repo = repo
        self.workspaces_dir = Path(workspaces_dir)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback

    def _progress(self, task_id: str, condition: str, step: str, message: str = ""):
        """Report progress if callback is set."""
        if self.progress_callback:
            self.progress_callback(task_id, condition, step, message)

    def run(self, task: Task, condition: Condition) -> TaskResult:
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

            skill_metrics = None

            # Generate AGENTS.md if with_skill
            if condition == Condition.WITH_SKILL:
                self._progress(task.id, cond_str, "skill_gen", "generating Intent Layer with Claude...")
                skill_result = run_claude(
                    workspace,
                    SKILL_GENERATION_PROMPT,
                    timeout=600
                )
                # Find created AGENTS.md/CLAUDE.md files
                files_created = self._find_agents_files(workspace)
                skill_metrics = SkillGenerationMetrics(
                    wall_clock_seconds=skill_result.wall_clock_seconds,
                    input_tokens=skill_result.input_tokens,
                    output_tokens=skill_result.output_tokens,
                    files_created=files_created
                )
                self._progress(task.id, cond_str, "skill_gen_done", f"created {len(files_created)} file(s) in {skill_result.wall_clock_seconds:.1f}s")

            # Build prompt (with AGENTS.md preamble if skill was generated)
            self._progress(task.id, cond_str, "prompt", "building prompt")
            prompt = self._build_prompt(task, workspace, condition)

            # Run Claude on the task
            self._progress(task.id, cond_str, "claude", "running Claude to fix the bug...")
            claude_result = run_claude(workspace, prompt)
            self._progress(task.id, cond_str, "claude_done", f"completed in {claude_result.wall_clock_seconds:.1f}s, {claude_result.tool_calls} tool calls")

            # Run tests
            self._progress(task.id, cond_str, "test", f"running tests: {self.repo.docker.test_command}")
            test_result = run_in_docker(
                workspace,
                self.repo.docker.image,
                self.repo.docker.test_command,
                timeout=120
            )
            test_status = "PASSED" if test_result.exit_code == 0 else "FAILED"
            self._progress(task.id, cond_str, "test_done", f"tests {test_status}")

            # Get diff stats
            self._progress(task.id, cond_str, "diff", "collecting diff stats")
            diff_stats = get_diff_stats(workspace)

            # Extract which AGENTS.md files were read during the fix
            agents_files_read = self._extract_agents_files_read(
                claude_result.stdout, workspace
            ) if condition == Condition.WITH_SKILL else None

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
                error=str(e)
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
        use_preamble = condition == Condition.WITH_SKILL

        if task.prompt_source == "commit_message":
            message = get_commit_message(workspace, task.fix_commit)
            return build_prompt_from_commit_message(message, with_agents_preamble=use_preamble)

        elif task.prompt_source == "failing_test":
            # Run the test to get failure output
            test_cmd = self.repo.docker.test_command
            if task.test_pattern:
                test_cmd = f"{test_cmd} -k '{task.test_pattern}'"

            result = run_in_docker(
                workspace,
                self.repo.docker.image,
                test_cmd,
                timeout=60
            )
            return build_prompt_from_failing_test(
                result.stdout + result.stderr, with_agents_preamble=use_preamble
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
