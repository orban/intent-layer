# lib/task_runner.py
from __future__ import annotations
import os
import tempfile
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lib.models import Task, RepoConfig
from lib.git_ops import clone_repo, checkout_commit, get_commit_message, get_diff_stats
from lib.docker_runner import run_in_docker
from lib.claude_runner import run_claude
from lib.prompt_builder import (
    build_prompt_from_commit_message,
    build_prompt_from_failing_test,
    build_prompt_from_issue
)


class Condition(Enum):
    WITH_SKILL = "with_skill"
    WITHOUT_SKILL = "without_skill"


@dataclass
class SkillGenerationMetrics:
    wall_clock_seconds: float
    input_tokens: int
    output_tokens: int


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
    error: str | None = None


class TaskRunner:
    def __init__(self, repo: RepoConfig, workspaces_dir: str):
        self.repo = repo
        self.workspaces_dir = Path(workspaces_dir)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    def run(self, task: Task, condition: Condition) -> TaskResult:
        """Execute a single task under the given condition."""
        workspace = self._setup_workspace(task, condition)

        try:
            # Setup: clone and checkout
            clone_repo(self.repo.url, workspace, shallow=False)
            checkout_commit(workspace, task.pre_fix_commit)

            # Run docker setup
            for setup_cmd in self.repo.docker.setup:
                run_in_docker(workspace, self.repo.docker.image, setup_cmd)

            skill_metrics = None

            # Generate AGENTS.md if with_skill
            if condition == Condition.WITH_SKILL:
                skill_result = run_claude(
                    workspace,
                    "Use the intent-layer skill to create an AGENTS.md for this codebase.",
                    timeout=600
                )
                skill_metrics = SkillGenerationMetrics(
                    wall_clock_seconds=skill_result.wall_clock_seconds,
                    input_tokens=skill_result.input_tokens,
                    output_tokens=skill_result.output_tokens
                )

            # Build prompt
            prompt = self._build_prompt(task, workspace)

            # Run Claude on the task
            claude_result = run_claude(workspace, prompt)

            # Run tests
            test_result = run_in_docker(
                workspace,
                self.repo.docker.image,
                self.repo.docker.test_command,
                timeout=120
            )

            # Get diff stats
            diff_stats = get_diff_stats(workspace)

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
                skill_generation=skill_metrics
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

    def _build_prompt(self, task: Task, workspace: str) -> str:
        """Build the appropriate prompt based on task config."""
        if task.prompt_source == "commit_message":
            message = get_commit_message(workspace, task.fix_commit)
            return build_prompt_from_commit_message(message)

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
            return build_prompt_from_failing_test(result.stdout + result.stderr)

        elif task.prompt_source == "issue":
            # TODO: Implement GitHub issue fetching
            raise NotImplementedError("Issue-based prompts not yet implemented")

        else:
            raise ValueError(f"Unknown prompt_source: {task.prompt_source}")
