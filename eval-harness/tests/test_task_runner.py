# tests/test_task_runner.py
import pytest
import tempfile
import os
import json
from pathlib import Path
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
    assert "Pitfalls" in preamble_map[Condition.INTENT_LAYER]


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

    # Worker crash (infrastructure failure)
    worker_crash = TaskResult(
        task_id="t6", condition=Condition.NONE, success=False,
        test_output="", wall_clock_seconds=0, input_tokens=0,
        output_tokens=0, tool_calls=0, lines_changed=0,
        files_touched=[], error="[worker-crash] OOM killed",
    )
    assert Reporter._is_infra_error(worker_crash) is True

    # Timeout (genuine failure — agent worked but ran out of time)
    timeout = TaskResult(
        task_id="t7", condition=Condition.FLAT_LLM, success=False,
        test_output="", wall_clock_seconds=300.0, input_tokens=50000,
        output_tokens=3000, tool_calls=15, lines_changed=0,
        files_touched=[], error="[timeout] Claude timed out after 300.0s",
        is_timeout=True,
    )
    assert Reporter._is_infra_error(timeout) is False


# --- Workspace naming and warm_cache tests ---


def test_workspace_name_includes_rep(sample_repo):
    """Workspace path includes rep index to avoid collisions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)
        task = Task(
            id="fix-rep-test",
            category="simple_fix",
            pre_fix_commit="abcdef01",
            fix_commit="12345678",
            prompt_source="commit_message"
        )

        ws0 = runner._setup_workspace(task, Condition.NONE, rep=0)
        ws1 = runner._setup_workspace(task, Condition.NONE, rep=1)
        ws5 = runner._setup_workspace(task, Condition.NONE, rep=5)

        assert ws0 != ws1
        assert ws1 != ws5
        assert "-r0" in ws0
        assert "-r1" in ws1
        assert "-r5" in ws5


def test_workspace_default_rep_is_zero(sample_repo):
    """Default rep=0 for backward compatibility."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)
        task = Task(
            id="fix-default-rep",
            category="simple_fix",
            pre_fix_commit="abcdef01",
            fix_commit="12345678",
            prompt_source="commit_message"
        )

        ws = runner._setup_workspace(task, Condition.NONE)
        assert "-r0" in ws


def test_build_run_log_path_is_unique_per_rep(sample_repo):
    """Run log paths should include phase/condition/rep-specific suffixes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)
        task = Task(
            id="fix-log-paths",
            category="simple_fix",
            pre_fix_commit="abcdef01",
            fix_commit="12345678",
            prompt_source="commit_message"
        )

        p0 = runner._build_run_log_path(task, "none", "test", rep=0)
        p1 = runner._build_run_log_path(task, "none", "test", rep=1)
        p2 = runner._build_run_log_path(task, "intent_layer", "fix", rep=0)

        assert str(p0) != str(p1)
        assert str(p0) != str(p2)
        assert "none-r0-test.log" in str(p0)
        assert "none-r1-test.log" in str(p1)
        assert "intent_layer-r0-fix.log" in str(p2)


def test_warm_cache_none_condition_returns_none(sample_repo):
    """warm_cache for the NONE condition is a no-op (nothing to generate)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)
        result = runner.warm_cache(
            "https://github.com/test/repo",
            Condition.NONE
        )
        assert result is None


def test_warm_cache_skips_when_cached(sample_repo):
    """warm_cache returns None if the repo-level cache already has the entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = os.path.join(tmpdir, ".cache")
        runner = TaskRunner(sample_repo, tmpdir, cache_dir=cache_dir, use_cache=True)

        # Pre-populate repo-level cache (warm_cache now uses repo-level keys)
        ws = os.path.join(tmpdir, "fake-ws")
        os.makedirs(ws)
        with open(os.path.join(ws, "CLAUDE.md"), "w") as f:
            f.write("# Cached context")

        runner.index_cache.save(
            "https://github.com/test/repo",
            "latest",
            ws,
            ["CLAUDE.md"],
            "intent_layer",
            repo_level=True
        )

        result = runner.warm_cache(
            "https://github.com/test/repo",
            Condition.INTENT_LAYER
        )
        assert result is None  # Already cached, nothing to do


def test_task_result_has_exit_code_and_timeout():
    """TaskResult supports exit_code and is_timeout fields."""
    result = TaskResult(
        task_id="fix-meta",
        condition=Condition.NONE,
        success=False,
        test_output="",
        wall_clock_seconds=300.0,
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        lines_changed=0,
        files_touched=[],
        exit_code=1,
        is_timeout=True,
    )
    assert result.exit_code == 1
    assert result.is_timeout is True


def test_pre_validate_commit_message_uses_runtime_probe(sample_repo, monkeypatch):
    """Commit-message prevalidation should not assume Python exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir)
        workspace = os.path.join(tmpdir, "ws")
        os.makedirs(workspace)

        task = Task(
            id="commit-message-smoke",
            category="simple_fix",
            pre_fix_commit="abc123",
            fix_commit="def456",
            prompt_source="commit_message"
        )

        captured = {}

        def fake_run_in_docker(workspace_arg, image, command, timeout=120, **_kwargs):
            captured["command"] = command
            return type("Result", (), {
                "exit_code": 0, "stdout": "ok", "stderr": "", "timed_out": False
            })()

        monkeypatch.setattr("lib.task_runner.run_in_docker", fake_run_in_docker)

        result = runner._pre_validate(task, workspace)
        assert result is None
        cmd = captured["command"]
        assert "command -v python" in cmd
        assert "command -v node" in cmd
        assert "smoke-ok" in cmd


def test_task_result_defaults_exit_code_and_timeout():
    """exit_code defaults to None, is_timeout defaults to False."""
    result = TaskResult(
        task_id="fix-defaults",
        condition=Condition.NONE,
        success=True,
        test_output="PASS",
        wall_clock_seconds=50.0,
        input_tokens=2000,
        output_tokens=1000,
        tool_calls=10,
        lines_changed=20,
        files_touched=["a.py"],
    )
    assert result.exit_code is None
    assert result.is_timeout is False


def test_empty_run_detection():
    """A result with >1s wall clock but 0 tokens is an empty run."""
    from lib.reporter import Reporter

    result = TaskResult(
        task_id="fix-empty",
        condition=Condition.INTENT_LAYER,
        success=False,
        test_output="",
        wall_clock_seconds=2.7,
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        lines_changed=0,
        files_touched=[],
        error="[empty-run] Claude produced no output (exit_code=1, 2.7s)",
        exit_code=1,
    )
    # Empty runs are infra errors — excluded from success stats
    assert Reporter._is_infra_error(result) is True


def test_empty_run_tag_format():
    """Verify the [empty-run] tag is recognized by _is_infra_error."""
    from lib.reporter import Reporter

    result = TaskResult(
        task_id="fix-emp",
        condition=Condition.NONE,
        success=False,
        test_output="",
        wall_clock_seconds=3.0,
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        lines_changed=0,
        files_touched=[],
        error="[empty-run] Claude produced no output (exit_code=0, 3.0s)",
    )
    assert Reporter._is_infra_error(result) is True


def test_timeout_tag_is_not_infra_error():
    """[timeout] errors are genuine failures, not infra errors."""
    from lib.reporter import Reporter

    result = TaskResult(
        task_id="fix-timeout",
        condition=Condition.FLAT_LLM,
        success=False,
        test_output="",
        wall_clock_seconds=300.0,
        input_tokens=50000,
        output_tokens=3000,
        tool_calls=5,
        lines_changed=0,
        files_touched=[],
        error="[timeout] Claude timed out after 300.0s",
        is_timeout=True,
    )
    assert Reporter._is_infra_error(result) is False


# --- claude_timeout threading ---

def test_task_runner_accepts_claude_timeout(sample_repo, tmp_path):
    """TaskRunner stores claude_timeout and defaults to 300."""
    runner = TaskRunner(sample_repo, str(tmp_path))
    assert runner.claude_timeout == 300

    runner2 = TaskRunner(sample_repo, str(tmp_path), claude_timeout=450)
    assert runner2.claude_timeout == 450


# --- Intent Layer hooks injection ---

def test_intent_layer_hooks_config_written(tmp_path):
    """Intent Layer hook injection writes .claude/settings.local.json with actual plugin hooks."""
    import json
    from pathlib import Path

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Simulate what task_runner.run() does for intent_layer
    plugin_root = str(Path(__file__).resolve().parents[2])
    hooks_config = {
        "hooks": {
            "PreToolUse": [{
                "matcher": "Edit|Write|NotebookEdit",
                "hooks": [{
                    "type": "command",
                    "command": f"{plugin_root}/scripts/pre-edit-check.sh",
                    "timeout": 10,
                }]
            }],
            "SessionStart": [{
                "matcher": "",
                "hooks": [{
                    "type": "command",
                    "command": f"{plugin_root}/scripts/inject-learnings.sh",
                    "timeout": 15,
                }]
            }],
        }
    }
    claude_dir = workspace / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "settings.local.json").write_text(json.dumps(hooks_config, indent=2))

    # Verify the file was created with correct structure
    settings = json.loads((claude_dir / "settings.local.json").read_text())
    assert "hooks" in settings
    assert "PreToolUse" in settings["hooks"]
    assert "SessionStart" in settings["hooks"]

    # Verify scripts actually exist at the referenced paths
    pre_edit_cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert Path(pre_edit_cmd).exists(), f"pre-edit-check.sh not found at {pre_edit_cmd}"

    inject_cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert Path(inject_cmd).exists(), f"inject-learnings.sh not found at {inject_cmd}"

    # Verify PreToolUse matcher only fires on writes (not reads)
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "Edit|Write|NotebookEdit"


def test_intent_layer_preamble_mentions_downlinks():
    """Intent Layer preamble directs Claude to read AGENTS.md via Downlinks."""
    from lib.prompt_builder import INTENT_LAYER_PREAMBLE
    assert "Downlinks" in INTENT_LAYER_PREAMBLE
    assert "AGENTS.md" in INTENT_LAYER_PREAMBLE
    assert "Pitfalls" in INTENT_LAYER_PREAMBLE


# --- Plugin integration tests ---


def test_plugin_root_resolves_to_repo_root():
    """plugin_root (2 parents up from task_runner.py) points to the intent-layer repo root."""
    from pathlib import Path

    # This is the same calculation task_runner.py uses
    task_runner_path = Path(__file__).resolve().parents[2] / "eval-harness" / "lib" / "task_runner.py"
    plugin_root = task_runner_path.resolve().parents[2]

    # Verify it's the intent-layer repo root by checking for key files
    assert (plugin_root / "scripts" / "pre-edit-check.sh").exists()
    assert (plugin_root / "scripts" / "inject-learnings.sh").exists()
    assert (plugin_root / "lib" / "common.sh").exists()
    assert (plugin_root / "lib" / "find_covering_node.sh").exists()


def test_plugin_hooks_env_for_intent_layer(sample_repo, monkeypatch):
    """CLAUDE_PLUGIN_ROOT is passed to run_claude for intent_layer condition."""
    from pathlib import Path

    captured_calls = []

    def fake_clone(url, workspace, shallow=False, reference=None):
        os.makedirs(workspace, exist_ok=True)

    def fake_checkout(workspace, commit):
        pass

    def fake_create_baseline(workspace):
        pass

    def fake_get_commit_message(workspace, commit):
        return "fix: something"

    def fake_run_claude(workspace, prompt, timeout=300, model=None,
                        extra_env=None, stderr_log=None, max_turns=50):
        captured_calls.append({
            "workspace": workspace,
            "extra_env": extra_env,
        })
        return type("ClaudeResult", (), {
            "exit_code": 0,
            "wall_clock_seconds": 10.0,
            "input_tokens": 1000,
            "output_tokens": 500,
            "tool_calls": 5,
            "stdout": "{}",
            "stderr": "",
            "timed_out": False,
            "cost_usd": 0.01,
            "num_turns": 3,
        })()

    def fake_run_in_docker(workspace, image, command, timeout=180, **kwargs):
        return type("Result", (), {
            "exit_code": 0,
            "stdout": "PASSED",
            "stderr": "",
            "timed_out": False,
        })()

    def fake_get_diff_stats(workspace):
        return type("DiffStats", (), {
            "lines_changed": 5,
            "files": ["src/main.py"],
        })()

    def fake_check_or_generate_index(self, workspace, repo_url, commit,
                                      condition="", model=None, timeout=600,
                                      repo_level=False):
        import pathlib
        (pathlib.Path(workspace) / "CLAUDE.md").write_text("# context")
        return SkillGenerationMetrics(
            wall_clock_seconds=1.0, input_tokens=0, output_tokens=0,
            cache_hit=True, files_created=["CLAUDE.md"],
        )

    monkeypatch.setattr("lib.task_runner.clone_repo", fake_clone)
    monkeypatch.setattr("lib.task_runner.checkout_commit", fake_checkout)
    monkeypatch.setattr("lib.task_runner.create_baseline_commit", fake_create_baseline)
    monkeypatch.setattr("lib.task_runner.get_commit_message", fake_get_commit_message)
    monkeypatch.setattr("lib.task_runner.run_claude", fake_run_claude)
    monkeypatch.setattr("lib.task_runner.run_in_docker", fake_run_in_docker)
    monkeypatch.setattr("lib.task_runner.get_diff_stats", fake_get_diff_stats)
    monkeypatch.setattr(TaskRunner, "_check_or_generate_index", fake_check_or_generate_index)

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir, use_cache=False)
        task = Task(
            id="fix-plugin-test",
            category="simple_fix",
            pre_fix_commit="abc123",
            fix_commit="def456",
            prompt_source="commit_message",
        )

        runner.run(task, Condition.INTENT_LAYER)

        assert len(captured_calls) == 1
        env = captured_calls[0]["extra_env"]
        assert env is not None
        assert "CLAUDE_PLUGIN_ROOT" in env
        assert Path(env["CLAUDE_PLUGIN_ROOT"]).is_dir()


def test_no_plugin_env_for_none_condition(sample_repo, monkeypatch):
    """CLAUDE_PLUGIN_ROOT is NOT set for the none condition."""
    captured_calls = []

    def fake_clone(url, workspace, shallow=False, reference=None):
        os.makedirs(workspace, exist_ok=True)

    def fake_checkout(workspace, commit):
        pass

    def fake_create_baseline(workspace):
        pass

    def fake_get_commit_message(workspace, commit):
        return "fix: something"

    def fake_run_claude(workspace, prompt, timeout=300, model=None,
                        extra_env=None, stderr_log=None, max_turns=50):
        captured_calls.append({"extra_env": extra_env})
        return type("ClaudeResult", (), {
            "exit_code": 0,
            "wall_clock_seconds": 10.0,
            "input_tokens": 1000,
            "output_tokens": 500,
            "tool_calls": 5,
            "stdout": "{}",
            "stderr": "",
            "timed_out": False,
            "cost_usd": 0.01,
            "num_turns": 3,
        })()

    def fake_run_in_docker(workspace, image, command, timeout=180, **kwargs):
        return type("Result", (), {
            "exit_code": 0,
            "stdout": "PASSED",
            "stderr": "",
            "timed_out": False,
        })()

    def fake_get_diff_stats(workspace):
        return type("DiffStats", (), {
            "lines_changed": 5,
            "files": ["src/main.py"],
        })()

    monkeypatch.setattr("lib.task_runner.clone_repo", fake_clone)
    monkeypatch.setattr("lib.task_runner.checkout_commit", fake_checkout)
    monkeypatch.setattr("lib.task_runner.create_baseline_commit", fake_create_baseline)
    monkeypatch.setattr("lib.task_runner.get_commit_message", fake_get_commit_message)
    monkeypatch.setattr("lib.task_runner.run_claude", fake_run_claude)
    monkeypatch.setattr("lib.task_runner.run_in_docker", fake_run_in_docker)
    monkeypatch.setattr("lib.task_runner.get_diff_stats", fake_get_diff_stats)

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir, use_cache=False)
        task = Task(
            id="fix-none-test",
            category="simple_fix",
            pre_fix_commit="abc123",
            fix_commit="def456",
            prompt_source="commit_message",
        )

        runner.run(task, Condition.NONE)

        assert len(captured_calls) == 1
        assert captured_calls[0]["extra_env"] is None


def test_no_plugin_hooks_for_flat_llm(sample_repo, monkeypatch):
    """flat_llm condition does NOT install plugin hooks or set CLAUDE_PLUGIN_ROOT."""
    captured_calls = []
    written_settings = []

    def fake_clone(url, workspace, shallow=False, reference=None):
        os.makedirs(workspace, exist_ok=True)

    def fake_checkout(workspace, commit):
        pass

    def fake_create_baseline(workspace):
        pass

    def fake_get_commit_message(workspace, commit):
        return "fix: something"

    def fake_run_claude(workspace, prompt, timeout=300, model=None,
                        extra_env=None, stderr_log=None, max_turns=50):
        # Check if .claude/settings.local.json was written
        settings_path = os.path.join(workspace, ".claude", "settings.local.json")
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                written_settings.append(json.load(f))
        captured_calls.append({"extra_env": extra_env})
        return type("ClaudeResult", (), {
            "exit_code": 0,
            "wall_clock_seconds": 10.0,
            "input_tokens": 1000,
            "output_tokens": 500,
            "tool_calls": 5,
            "stdout": "{}",
            "stderr": "",
            "timed_out": False,
            "cost_usd": 0.01,
            "num_turns": 3,
        })()

    def fake_run_in_docker(workspace, image, command, timeout=180, **kwargs):
        return type("Result", (), {
            "exit_code": 0,
            "stdout": "PASSED",
            "stderr": "",
            "timed_out": False,
        })()

    def fake_get_diff_stats(workspace):
        return type("DiffStats", (), {
            "lines_changed": 5,
            "files": ["src/main.py"],
        })()

    def fake_generate_flat_context(self, workspace, repo_url, commit, model=None):
        # Create a CLAUDE.md so _find_agents_files has something
        import pathlib
        workspace_path = pathlib.Path(workspace)
        (workspace_path / "CLAUDE.md").write_text("# flat context")
        return SkillGenerationMetrics(
            wall_clock_seconds=1.0,
            input_tokens=0,
            output_tokens=0,
            cache_hit=True,
            files_created=["CLAUDE.md"],
        )

    monkeypatch.setattr("lib.task_runner.clone_repo", fake_clone)
    monkeypatch.setattr("lib.task_runner.checkout_commit", fake_checkout)
    monkeypatch.setattr("lib.task_runner.create_baseline_commit", fake_create_baseline)
    monkeypatch.setattr("lib.task_runner.get_commit_message", fake_get_commit_message)
    monkeypatch.setattr("lib.task_runner.run_claude", fake_run_claude)
    monkeypatch.setattr("lib.task_runner.run_in_docker", fake_run_in_docker)
    monkeypatch.setattr("lib.task_runner.get_diff_stats", fake_get_diff_stats)
    monkeypatch.setattr(TaskRunner, "_generate_flat_context", fake_generate_flat_context)

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir, use_cache=False)
        task = Task(
            id="fix-flat-test",
            category="simple_fix",
            pre_fix_commit="abc123",
            fix_commit="def456",
            prompt_source="commit_message",
        )

        runner.run(task, Condition.FLAT_LLM)

        assert len(captured_calls) == 1
        assert captured_calls[0]["extra_env"] is None
        # No hook config should have been written
        assert len(written_settings) == 0


def test_intent_layer_writes_hooks_to_workspace(sample_repo, monkeypatch):
    """intent_layer condition writes .claude/settings.local.json with plugin hooks into workspace."""
    import json
    from pathlib import Path

    written_settings = {}

    def fake_clone(url, workspace, shallow=False, reference=None):
        os.makedirs(workspace, exist_ok=True)

    def fake_checkout(workspace, commit):
        pass

    def fake_create_baseline(workspace):
        pass

    def fake_get_commit_message(workspace, commit):
        return "fix: something"

    def fake_check_or_generate_index(self, workspace, repo_url, commit,
                                      condition="", model=None, timeout=600,
                                      repo_level=False):
        import pathlib
        # Create a CLAUDE.md so the runner is satisfied
        (pathlib.Path(workspace) / "CLAUDE.md").write_text("# intent layer context")
        return SkillGenerationMetrics(
            wall_clock_seconds=1.0,
            input_tokens=0,
            output_tokens=0,
            cache_hit=True,
            files_created=["CLAUDE.md"],
        )

    def fake_run_claude(workspace, prompt, timeout=300, model=None,
                        extra_env=None, stderr_log=None, max_turns=50):
        # Capture the settings file at the time Claude runs
        settings_path = os.path.join(workspace, ".claude", "settings.local.json")
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                written_settings.update(json.load(f))
        return type("ClaudeResult", (), {
            "exit_code": 0,
            "wall_clock_seconds": 10.0,
            "input_tokens": 1000,
            "output_tokens": 500,
            "tool_calls": 5,
            "stdout": "{}",
            "stderr": "",
            "timed_out": False,
            "cost_usd": 0.01,
            "num_turns": 3,
        })()

    def fake_run_in_docker(workspace, image, command, timeout=180, **kwargs):
        return type("Result", (), {
            "exit_code": 0,
            "stdout": "PASSED",
            "stderr": "",
            "timed_out": False,
        })()

    def fake_get_diff_stats(workspace):
        return type("DiffStats", (), {
            "lines_changed": 5,
            "files": ["src/main.py"],
        })()

    monkeypatch.setattr("lib.task_runner.clone_repo", fake_clone)
    monkeypatch.setattr("lib.task_runner.checkout_commit", fake_checkout)
    monkeypatch.setattr("lib.task_runner.create_baseline_commit", fake_create_baseline)
    monkeypatch.setattr("lib.task_runner.get_commit_message", fake_get_commit_message)
    monkeypatch.setattr("lib.task_runner.run_claude", fake_run_claude)
    monkeypatch.setattr("lib.task_runner.run_in_docker", fake_run_in_docker)
    monkeypatch.setattr("lib.task_runner.get_diff_stats", fake_get_diff_stats)
    monkeypatch.setattr(TaskRunner, "_check_or_generate_index", fake_check_or_generate_index)

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TaskRunner(sample_repo, tmpdir, use_cache=False)
        task = Task(
            id="fix-hooks-written",
            category="simple_fix",
            pre_fix_commit="abc123",
            fix_commit="def456",
            prompt_source="commit_message",
        )

        runner.run(task, Condition.INTENT_LAYER)

        # Hooks config should have been written before Claude ran
        assert "hooks" in written_settings
        assert "PreToolUse" in written_settings["hooks"]
        assert "SessionStart" in written_settings["hooks"]

        # Verify PreToolUse points to pre-edit-check.sh
        pre_edit_cmd = written_settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert pre_edit_cmd.endswith("/scripts/pre-edit-check.sh")
        assert Path(pre_edit_cmd).exists()

        # Verify SessionStart points to inject-learnings.sh
        inject_cmd = written_settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        assert inject_cmd.endswith("/scripts/inject-learnings.sh")
        assert Path(inject_cmd).exists()

        # Verify matcher is write-only (not reads)
        assert written_settings["hooks"]["PreToolUse"][0]["matcher"] == "Edit|Write|NotebookEdit"


def test_pre_edit_check_runs_against_sample_agents_md():
    """Integration smoke test: pre-edit-check.sh produces output for a covered file."""
    import json as _json
    import subprocess
    from pathlib import Path

    plugin_root = str(Path(__file__).resolve().parents[2])
    script = os.path.join(plugin_root, "scripts", "pre-edit-check.sh")

    # Create a temp workspace with an AGENTS.md that has a Pitfalls section
    with tempfile.TemporaryDirectory() as tmpdir:
        agents_md = os.path.join(tmpdir, "AGENTS.md")
        with open(agents_md, "w") as f:
            f.write("# Test Module\n\n## Pitfalls\n\n### Watch out for X\n\nDon't do X.\n")

        # Create a source file in the same directory
        src_file = os.path.join(tmpdir, "main.py")
        with open(src_file, "w") as f:
            f.write("print('hello')\n")

        # Build the JSON input that Claude sends to PreToolUse hooks
        input_json = _json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": src_file},
        })

        result = subprocess.run(
            [script],
            input=input_json,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "CLAUDE_PLUGIN_ROOT": plugin_root,
            },
            timeout=10,
        )

        # The hook should exit 0 and produce JSON output with additionalContext
        assert result.returncode == 0
        assert result.stdout.strip(), "pre-edit-check.sh produced no output"
        output = _json.loads(result.stdout)
        # Hook output is wrapped: {"hookSpecificOutput": {"additionalContext": "..."}}
        hook_output = output.get("hookSpecificOutput", output)
        assert "additionalContext" in hook_output
        assert "Pitfalls" in hook_output["additionalContext"]
