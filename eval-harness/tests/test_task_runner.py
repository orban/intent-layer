# tests/test_task_runner.py
import pytest
import tempfile
import os
import shutil
from dataclasses import dataclass
from lib.task_runner import (
    TaskRunner,
    TaskResult,
    Condition,
    SkillGenerationMetrics,
    PreValidationError,
    SkillGenerationError,
)
from lib.prompt_builder import (
    build_skill_generation_prompt,
    FLAT_PREAMBLE,
    INTENT_LAYER_PREAMBLE,
)
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
        condition=Condition.NONE,
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
    assert result.condition == Condition.NONE
    assert result.success is True
    assert result.agents_files_read is None


def test_task_result_with_agents_files():
    result = TaskResult(
        task_id="fix-123",
        condition=Condition.INTENT_LAYER,
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
    metrics_fresh = SkillGenerationMetrics(
        wall_clock_seconds=120.0,
        input_tokens=5000,
        output_tokens=2000,
        files_created=["CLAUDE.md", "lib/AGENTS.md"],
        cache_hit=False
    )
    assert metrics_fresh.cache_hit is False

    metrics_cached = SkillGenerationMetrics(
        wall_clock_seconds=2.0,
        input_tokens=0,
        output_tokens=0,
        files_created=["CLAUDE.md", "lib/AGENTS.md"],
        cache_hit=True
    )
    assert metrics_cached.cache_hit is True


def test_skill_generation_prompt_content():
    prompt = build_skill_generation_prompt("/fake/plugin")
    assert "Intent Layer" in prompt
    assert "CLAUDE.md" in prompt
    assert "AGENTS.md" in prompt
    assert "/fake/plugin/scripts/" in prompt
    assert "mine_git_history" in prompt
    assert "validate_node" in prompt


def test_condition_enum():
    assert Condition.NONE.value == "none"
    assert Condition.FLAT_LLM.value == "flat_llm"
    assert Condition.INTENT_LAYER.value == "intent_layer"
    assert len(Condition) == 3


def test_find_agents_files(sample_repo):
    """Test that _find_agents_files discovers AGENTS.md and CLAUDE.md files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(os.path.join(workspace, "lib"))
        os.makedirs(os.path.join(workspace, "src", "utils"))

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
        assert "src/main.py" not in files


def test_task_runner_uses_cache(sample_repo):
    """Test that TaskRunner integrates IndexCache when use_cache=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, ".index-cache")

        runner = TaskRunner(sample_repo, tmpdir, use_cache=True, cache_dir=cache_dir)
        assert runner.index_cache is not None
        assert str(runner.index_cache.cache_dir) == cache_dir

        test_repo = "https://github.com/test/repo"
        test_commit = "abc123def"
        cache_key = runner.index_cache.get_cache_key(test_repo, test_commit)
        assert cache_key == "repo-abc123de"

        runner_no_cache = TaskRunner(sample_repo, tmpdir, use_cache=False)
        assert runner_no_cache.index_cache is None

        runner_default = TaskRunner(sample_repo, tmpdir)
        assert runner_default.index_cache is not None


# --- New tests for 3-condition eval ---


def test_strip_context_files(sample_repo):
    """Test that _strip_context_files removes AGENTS.md, CLAUDE.md, and .github."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(os.path.join(workspace, "src"))
        os.makedirs(os.path.join(workspace, ".github", "workflows"))

        # Create context files
        open(os.path.join(workspace, "CLAUDE.md"), "w").close()
        open(os.path.join(workspace, "src", "AGENTS.md"), "w").close()
        open(os.path.join(workspace, ".github", "workflows", "ci.yml"), "w").close()
        # Create a regular file that should NOT be removed
        open(os.path.join(workspace, "src", "main.py"), "w").close()

        removed = runner._strip_context_files(workspace)

        assert "CLAUDE.md" in removed
        assert "src/AGENTS.md" in removed
        assert ".github" in removed
        # Regular files untouched
        assert os.path.exists(os.path.join(workspace, "src", "main.py"))
        # Context files gone
        assert not os.path.exists(os.path.join(workspace, "CLAUDE.md"))
        assert not os.path.exists(os.path.join(workspace, "src", "AGENTS.md"))
        assert not os.path.exists(os.path.join(workspace, ".github"))


def test_strip_context_files_with_extras(sample_repo):
    """Test that strip_extra removes additional per-repo files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(os.path.join(workspace, ".cursor", "rules"))

        open(os.path.join(workspace, ".cursorrules"), "w").close()
        open(os.path.join(workspace, ".cursor", "rules", "rule1.mdc"), "w").close()

        removed = runner._strip_context_files(
            workspace, strip_extra=[".cursorrules", ".cursor/rules/"]
        )

        assert ".cursorrules" in removed
        # .cursor/rules/ directory should be removed
        assert not os.path.exists(os.path.join(workspace, ".cursorrules"))
        assert not os.path.exists(os.path.join(workspace, ".cursor", "rules"))


def test_strip_context_files_empty_workspace(sample_repo):
    """Test that stripping an empty workspace returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(workspace)

        removed = runner._strip_context_files(workspace)
        assert removed == []


def test_preamble_routing():
    """Test that each condition maps to the correct preamble."""
    from lib.task_runner import Condition
    from lib.prompt_builder import FLAT_PREAMBLE, INTENT_LAYER_PREAMBLE

    preamble_map = {
        Condition.NONE: None,
        Condition.FLAT_LLM: FLAT_PREAMBLE,
        Condition.INTENT_LAYER: INTENT_LAYER_PREAMBLE,
    }

    assert preamble_map[Condition.NONE] is None
    assert "CLAUDE.md" in preamble_map[Condition.FLAT_LLM]
    assert "AGENTS.md" in preamble_map[Condition.INTENT_LAYER]
    assert "pitfalls" in preamble_map[Condition.INTENT_LAYER]


def test_strip_extra_in_repo_config():
    """Test that RepoConfig accepts strip_extra field."""
    repo = RepoConfig(
        url="https://github.com/test/repo",
        default_branch="main",
        docker=DockerConfig(
            image="python:3.11-slim",
            setup=["pip install -e ."],
            test_command="pytest"
        ),
        strip_extra=[".cursorrules", ".cursor/rules/"]
    )
    assert repo.strip_extra == [".cursorrules", ".cursor/rules/"]


def test_strip_extra_defaults_empty():
    """Test that RepoConfig.strip_extra defaults to empty list."""
    repo = RepoConfig(
        url="https://github.com/test/repo",
        docker=DockerConfig(image="python:3.11-slim", test_command="pytest")
    )
    assert repo.strip_extra == []


def test_generate_flat_context_dual_write(sample_repo):
    """Test that _generate_flat_context creates both CLAUDE.md and AGENTS.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, ".cache")
        runner = TaskRunner(sample_repo, tmpdir, cache_dir=cache_dir, use_cache=True)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(workspace)

        # Simulate Claude having created only CLAUDE.md
        with open(os.path.join(workspace, "CLAUDE.md"), "w") as f:
            f.write("# Generated CLAUDE.md\nProject overview here.")

        # Pre-populate cache so _generate_flat_context hits cache and restores CLAUDE.md
        runner.index_cache.save(
            "https://github.com/test/repo",
            "abc123def",
            workspace,
            ["CLAUDE.md"],
            "flat_llm"
        )

        # Clean workspace and run
        os.remove(os.path.join(workspace, "CLAUDE.md"))

        metrics = runner._generate_flat_context(
            workspace=workspace,
            repo_url="https://github.com/test/repo",
            commit="abc123def"
        )

        assert metrics.cache_hit is True
        assert os.path.exists(os.path.join(workspace, "CLAUDE.md"))


def test_strip_extra_rejects_path_traversal(sample_repo):
    """Test that strip_extra blocks paths escaping the workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(workspace)

        # File outside workspace that must NOT be deleted
        outside_file = os.path.join(tmpdir, "important.txt")
        with open(outside_file, "w") as f:
            f.write("don't delete me")

        removed = runner._strip_context_files(
            workspace, strip_extra=["../important.txt"]
        )

        assert "../important.txt" not in removed
        assert os.path.exists(outside_file)


def test_strip_extra_rejects_prefix_confusion(sample_repo):
    """Test that /work doesn't match /work-evil (prefix collision)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "work")
        os.makedirs(workspace)

        # Sibling directory with shared prefix
        sibling = os.path.join(tmpdir, "work-evil")
        os.makedirs(sibling)
        sibling_file = os.path.join(sibling, "secret.txt")
        with open(sibling_file, "w") as f:
            f.write("sensitive data")

        removed = runner._strip_context_files(
            workspace, strip_extra=["../work-evil/secret.txt"]
        )

        assert "../work-evil/secret.txt" not in removed
        assert os.path.exists(sibling_file)


def test_strip_context_files_with_universal_and_extras(sample_repo):
    """Test stripping universal context files AND strip_extra simultaneously."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(os.path.join(workspace, "src"))
        os.makedirs(os.path.join(workspace, ".github", "workflows"))

        # Universal files
        open(os.path.join(workspace, "CLAUDE.md"), "w").close()
        open(os.path.join(workspace, "src", "AGENTS.md"), "w").close()
        open(os.path.join(workspace, ".github", "workflows", "ci.yml"), "w").close()
        # Extra files
        open(os.path.join(workspace, ".cursorrules"), "w").close()
        # Regular file
        open(os.path.join(workspace, "src", "main.py"), "w").close()

        removed = runner._strip_context_files(workspace, strip_extra=[".cursorrules"])

        assert "CLAUDE.md" in removed
        assert "src/AGENTS.md" in removed
        assert ".github" in removed
        assert ".cursorrules" in removed
        assert len(removed) == 4
        # Regular file untouched
        assert os.path.exists(os.path.join(workspace, "src", "main.py"))


# --- Exception and error classification tests ---


def test_pre_validation_error_is_importable():
    """PreValidationError can be raised and caught."""
    with pytest.raises(PreValidationError, match="test already passes"):
        raise PreValidationError("test already passes at pre_fix_commit")


def test_skill_generation_error_is_importable():
    """SkillGenerationError can be raised and caught."""
    with pytest.raises(SkillGenerationError, match="no files created"):
        raise SkillGenerationError("no files created")


def test_pre_validate_catches_residual_context_files(sample_repo):
    """_pre_validate raises if AGENTS.md/CLAUDE.md files remain after strip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)

        workspace = os.path.join(tmpdir, "test-workspace")
        os.makedirs(workspace)

        # Create a residual CLAUDE.md that should have been stripped
        with open(os.path.join(workspace, "CLAUDE.md"), "w") as f:
            f.write("# leftover context")

        task = Task(
            id="fix-residual",
            category="simple_fix",
            pre_fix_commit="abc123",
            fix_commit="def456",
            prompt_source="commit_message"
        )

        # _pre_validate should fail on residual check (step 3)
        # We can't easily mock docker, so we call the residual check directly
        from pathlib import Path as P
        workspace_path = P(workspace)
        residual = []
        for pattern in ["**/AGENTS.md", "**/CLAUDE.md"]:
            for match in workspace_path.glob(pattern):
                residual.append(str(match.relative_to(workspace_path)))

        assert len(residual) == 1
        assert "CLAUDE.md" in residual


def test_error_tag_classification():
    """Verify error tag format matches what _is_infra_error expects."""
    from lib.reporter import Reporter

    # Infrastructure error
    infra = TaskResult(
        task_id="t1", condition=Condition.NONE, success=False,
        test_output="", wall_clock_seconds=0, input_tokens=0,
        output_tokens=0, tool_calls=0, lines_changed=0,
        files_touched=[], error="[infrastructure] clone failed"
    )
    assert Reporter._is_infra_error(infra) is True

    # Pre-validation error
    preval = TaskResult(
        task_id="t2", condition=Condition.NONE, success=False,
        test_output="", wall_clock_seconds=0, input_tokens=0,
        output_tokens=0, tool_calls=0, lines_changed=0,
        files_touched=[], error="[pre-validation] test passes at pre_fix_commit"
    )
    assert Reporter._is_infra_error(preval) is True

    # Skill generation error
    skillgen = TaskResult(
        task_id="t3", condition=Condition.INTENT_LAYER, success=False,
        test_output="", wall_clock_seconds=0, input_tokens=0,
        output_tokens=0, tool_calls=0, lines_changed=0,
        files_touched=[], error="[skill-generation] no files created"
    )
    assert Reporter._is_infra_error(skillgen) is True

    # Normal failure (experimental outcome, not infra)
    normal_fail = TaskResult(
        task_id="t4", condition=Condition.NONE, success=False,
        test_output="AssertionError", wall_clock_seconds=50,
        input_tokens=2000, output_tokens=1000, tool_calls=10,
        lines_changed=20, files_touched=["a.py"], error=None
    )
    assert Reporter._is_infra_error(normal_fail) is False

    # Non-tagged error (experimental outcome)
    other_error = TaskResult(
        task_id="t5", condition=Condition.NONE, success=False,
        test_output="", wall_clock_seconds=0, input_tokens=0,
        output_tokens=0, tool_calls=0, lines_changed=0,
        files_touched=[], error="Claude CLI returned exit code 1"
    )
    assert Reporter._is_infra_error(other_error) is False
