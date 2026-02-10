# tests/test_task_runner.py
import pytest
import tempfile
import os
from dataclasses import dataclass
from lib.task_runner import (
    TaskRunner,
    TaskResult,
    Condition,
    SkillGenerationMetrics,
)
from lib.prompt_builder import build_skill_generation_prompt
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
    assert result.agents_files_read is None


def test_task_result_with_agents_files():
    result = TaskResult(
        task_id="fix-123",
        condition=Condition.WITH_SKILL,
        success=True,
        test_output="All tests passed",
        wall_clock_seconds=45.0,
        input_tokens=1000,
        output_tokens=500,
        tool_calls=10,
        lines_changed=25,
        files_touched=["src/main.py"],
        agents_files_read=["CLAUDE.md", "src/AGENTS.md"]
    )
    assert result.agents_files_read == ["CLAUDE.md", "src/AGENTS.md"]


def test_skill_generation_metrics():
    metrics = SkillGenerationMetrics(
        wall_clock_seconds=120.0,
        input_tokens=5000,
        output_tokens=2000,
        files_created=["CLAUDE.md", "lib/AGENTS.md"],
        cache_hit=False
    )
    assert metrics.files_created == ["CLAUDE.md", "lib/AGENTS.md"]


def test_skill_generation_metrics_with_cache_hit():
    """Test that SkillGenerationMetrics tracks cache_hit status."""
    # Cache miss (fresh generation)
    metrics_fresh = SkillGenerationMetrics(
        wall_clock_seconds=120.0,
        input_tokens=5000,
        output_tokens=2000,
        files_created=["CLAUDE.md", "lib/AGENTS.md"],
        cache_hit=False
    )
    assert metrics_fresh.cache_hit is False

    # Cache hit (restored from cache)
    metrics_cached = SkillGenerationMetrics(
        wall_clock_seconds=2.0,
        input_tokens=0,
        output_tokens=0,
        files_created=["CLAUDE.md", "lib/AGENTS.md"],
        cache_hit=True
    )
    assert metrics_cached.cache_hit is True


def test_skill_generation_prompt_content():
    # Verify the prompt contains key instructions
    prompt = build_skill_generation_prompt()
    assert "Intent Layer" in prompt
    assert "CLAUDE.md" in prompt
    assert "AGENTS.md" in prompt
    assert "git history" in prompt
    assert "Pitfalls" in prompt


def test_condition_enum():
    assert Condition.WITH_SKILL.value == "with_skill"
    assert Condition.WITHOUT_SKILL.value == "without_skill"


def test_find_agents_files(sample_repo):
    """Test that _find_agents_files discovers AGENTS.md and CLAUDE.md files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        # Create a mock workspace with AGENTS.md files
        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(os.path.join(workspace, "lib"))
        os.makedirs(os.path.join(workspace, "src", "utils"))

        # Create the files
        open(os.path.join(workspace, "CLAUDE.md"), "w").close()
        open(os.path.join(workspace, "lib", "AGENTS.md"), "w").close()
        open(os.path.join(workspace, "src", "utils", "AGENTS.md"), "w").close()

        files = runner._find_agents_files(workspace)

        assert "CLAUDE.md" in files
        assert "lib/AGENTS.md" in files
        assert "src/utils/AGENTS.md" in files


def test_extract_agents_files_read(sample_repo):
    """Test extraction of Read tool calls from Claude output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)
        workspace = "/test/workspace"

        # Mock Claude JSON output with Read tool calls
        claude_output = '''
        {
            "messages": [
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/test/workspace/CLAUDE.md"}
                        },
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/test/workspace/src/AGENTS.md"}
                        },
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/test/workspace/src/main.py"}
                        }
                    ]
                }
            ]
        }
        '''

        files = runner._extract_agents_files_read(claude_output, workspace)

        assert "CLAUDE.md" in files
        assert "src/AGENTS.md" in files
        # Regular files should not be included
        assert "src/main.py" not in files


def test_task_runner_uses_cache(sample_repo):
    """Test that TaskRunner integrates IndexCache when use_cache=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create cache directory
        cache_dir = os.path.join(tmpdir, ".index-cache")

        # Create TaskRunner with cache enabled
        runner = TaskRunner(sample_repo, tmpdir, use_cache=True, cache_dir=cache_dir)

        # Verify IndexCache instance is created
        assert runner.index_cache is not None
        assert str(runner.index_cache.cache_dir) == cache_dir

        # Verify cache methods work (create a proper cache entry)
        test_repo = "https://github.com/test/repo"
        test_commit = "abc123def"
        cache_key = runner.index_cache.get_cache_key(test_repo, test_commit)
        assert cache_key == "repo-abc123de"

        # Test with cache disabled
        runner_no_cache = TaskRunner(sample_repo, tmpdir, use_cache=False)
        assert runner_no_cache.index_cache is None

        # Test default behavior (cache enabled)
        runner_default = TaskRunner(sample_repo, tmpdir)
        assert runner_default.index_cache is not None
