# tests/test_task_runner.py
import pytest
from dataclasses import dataclass
from lib.task_runner import TaskRunner, TaskResult, Condition
from lib.models import Task, RepoConfig, DockerConfig


@pytest.fixture
def sample_task():
    return Task(
        id="fix-bug-123",
        category="simple_fix",
        pre_fix_commit="abc123",
        fix_commit="def456",
        prompt_source="commit_message"
    )


@pytest.fixture
def sample_repo():
    return RepoConfig(
        url="https://github.com/test/repo",
        default_branch="main",
        docker=DockerConfig(
            image="node:20-slim",
            setup=["npm install"],
            test_command="npm test"
        )
    )


def test_task_result_structure():
    result = TaskResult(
        task_id="fix-123",
        condition=Condition.WITHOUT_SKILL,
        success=True,
        test_output="All tests passed",
        wall_clock_seconds=45.0,
        input_tokens=1000,
        output_tokens=500,
        tool_calls=10,
        lines_changed=25,
        files_touched=["src/main.py"]
    )
    assert result.task_id == "fix-123"
    assert result.condition == Condition.WITHOUT_SKILL
    assert result.success is True


def test_condition_enum():
    assert Condition.WITH_SKILL.value == "with_skill"
    assert Condition.WITHOUT_SKILL.value == "without_skill"
