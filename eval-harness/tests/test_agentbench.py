# tests/test_agentbench.py
"""Tests for AGENTbench loader and runner."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from lib.agentbench_loader import AgentbenchInstance, load_instances
from lib.agentbench_runner import (
    strip_docs,
    write_test_infrastructure,
    _parse_test_results,
    evaluate_instance,
    build_prompt,
)
from lib.task_runner import Condition


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_instance(**overrides) -> AgentbenchInstance:
    """Build an AgentbenchInstance with sensible defaults."""
    defaults = dict(
        instance_id="ansible_ansible-83217",
        repo="ansible_ansible",
        base_repo="ansible/ansible",
        base_sha="abc123def456",
        docker_image="ghcr.io/eth-sri/agent-bench:ansible_ansible",
        problem_description="Fix the bug in module_utils.",
        setup_commands=["pip install -e ."],
        test_files=(("tests/test_foo.py", "def test_foo(): pass"),),
        test_commands=["python run_pr_tests.py"],
        test_file_runner="#!/usr/bin/env python\nprint('run pr tests')",
        repo_test_runner="#!/usr/bin/env python\nprint('run repo tests')",
        repo_test_commands=["python run_tests.py"],
        repo_test_after_pr_patch={"test_foo::test_bar": True},
        clean_pr_patch=None,
    )
    defaults.update(overrides)
    return AgentbenchInstance(**defaults)


def _make_hf_row(**overrides) -> dict:
    """Build a HuggingFace row dict that load_instances() parses."""
    defaults = dict(
        instance_id="ansible_ansible-83217",
        repo="ansible_ansible",
        base_repo="ansible/ansible",
        base_sha="abc123",
        docker_image="ghcr.io/eth-sri/agent-bench:ansible_ansible",
        problem_description="Fix it.",
        setup_commands=["pip install -e ."],
        test_file_names=["tests/test_foo.py"],
        test_file_contents=["def test_foo(): pass"],
        test_commands=["python run_pr_tests.py"],
        test_file_runner="runner code",
        repo_test_runner="repo runner code",
        repo_test_commands=["python run_tests.py"],
        repo_test_after_pr_patch='{"test_a": true}',
        clean_pr_patch=None,
    )
    defaults.update(overrides)
    return defaults


# ── Loader tests ──────────────────────────────────────────────────────


class TestLoadInstances:

    def _mock_dataset(self, rows: list[dict]):
        """Patch datasets.load_dataset (locally imported by loader)."""
        ds = MagicMock()
        ds.__iter__ = lambda self: iter(rows)
        ds.__len__ = lambda self: len(rows)
        return patch("datasets.load_dataset", return_value=ds)

    def test_basic_load(self):
        row = _make_hf_row()
        with self._mock_dataset([row]):
            instances = load_instances()
        assert len(instances) == 1
        inst = instances[0]
        assert inst.instance_id == "ansible_ansible-83217"
        assert inst.repo == "ansible_ansible"
        assert inst.base_repo == "ansible/ansible"
        assert inst.test_files == (("tests/test_foo.py", "def test_foo(): pass"),)
        assert inst.repo_test_after_pr_patch == {"test_a": True}

    def test_filter_by_repo(self):
        rows = [
            _make_hf_row(instance_id="a-1", repo="repo_a"),
            _make_hf_row(instance_id="b-1", repo="repo_b"),
            _make_hf_row(instance_id="a-2", repo="repo_a"),
        ]
        with self._mock_dataset(rows):
            instances = load_instances(filter_repo="repo_a")
        assert len(instances) == 2
        assert all(i.repo == "repo_a" for i in instances)

    def test_filter_by_ids(self):
        rows = [
            _make_hf_row(instance_id="a-1"),
            _make_hf_row(instance_id="a-2"),
            _make_hf_row(instance_id="a-3"),
        ]
        with self._mock_dataset(rows):
            instances = load_instances(filter_ids=["a-1", "a-3"])
        assert [i.instance_id for i in instances] == ["a-1", "a-3"]

    def test_mismatched_test_files_skipped(self):
        row = _make_hf_row(
            test_file_names=["a.py", "b.py"],
            test_file_contents=["content_a"],  # only 1 content for 2 names
        )
        with self._mock_dataset([row]):
            instances = load_instances()
        assert len(instances) == 0

    def test_bad_json_in_repo_test_after_pr_patch(self):
        row = _make_hf_row(repo_test_after_pr_patch="not valid json{")
        with self._mock_dataset([row]):
            instances = load_instances()
        assert len(instances) == 1
        assert instances[0].repo_test_after_pr_patch == {}

    def test_dict_repo_test_after_pr_patch(self):
        """repo_test_after_pr_patch can be a dict (not JSON string)."""
        row = _make_hf_row(repo_test_after_pr_patch={"test_x": False})
        with self._mock_dataset([row]):
            instances = load_instances()
        assert instances[0].repo_test_after_pr_patch == {"test_x": False}

    def test_multiple_test_files_zipped(self):
        row = _make_hf_row(
            test_file_names=["tests/a.py", "tests/b.py"],
            test_file_contents=["content_a", "content_b"],
        )
        with self._mock_dataset([row]):
            instances = load_instances()
        assert instances[0].test_files == (
            ("tests/a.py", "content_a"),
            ("tests/b.py", "content_b"),
        )

    def test_frozen_instance(self):
        inst = _make_instance()
        with pytest.raises(AttributeError):
            inst.instance_id = "new_id"  # type: ignore[misc]


# ── Runner: strip_docs ────────────────────────────────────────────────


class TestStripDocs:

    def test_strips_md_files(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "README.md").write_text("readme")
            (ws / "CONTRIBUTING.md").write_text("contrib")
            (ws / "src").mkdir()
            (ws / "src" / "main.py").write_text("code")
            (ws / "src" / "notes.md").write_text("notes")

            count = strip_docs(ws)

            assert count == 2  # CONTRIBUTING.md, src/notes.md (README.md preserved)
            assert (ws / "README.md").exists()  # preserved for setup.py
            assert not (ws / "CONTRIBUTING.md").exists()
            assert not (ws / "src" / "notes.md").exists()
            assert (ws / "src" / "main.py").exists()

    def test_strips_special_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            for dirname in (".github", "docs", ".claude", ".cursor", ".codex"):
                (ws / dirname).mkdir()
                (ws / dirname / "file.txt").write_text("content")

            count = strip_docs(ws)

            assert count == 5
            for dirname in (".github", "docs", ".claude", ".cursor", ".codex"):
                assert not (ws / dirname).exists()

    def test_no_docs_returns_zero(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "src.py").write_text("code")
            assert strip_docs(ws) == 0


# ── Runner: write_test_infrastructure ──────────────────────────────────


class TestWriteTestInfrastructure:

    def test_writes_test_files_and_runners(self):
        inst = _make_instance(
            test_files=(
                ("tests/test_foo.py", "test content foo"),
                ("tests/sub/test_bar.py", "test content bar"),
            ),
            test_file_runner="pr runner script",
            repo_test_runner="repo runner script",
        )
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            write_test_infrastructure(ws, inst)

            assert (ws / "tests" / "test_foo.py").read_text() == "test content foo"
            assert (ws / "tests" / "sub" / "test_bar.py").read_text() == "test content bar"
            assert (ws / "run_pr_tests.py").read_text() == "pr runner script"
            assert (ws / "run_tests.py").read_text() == "repo runner script"
            # Check executable permissions
            import stat
            assert (ws / "run_pr_tests.py").stat().st_mode & stat.S_IXUSR

    def test_path_traversal_blocked(self):
        """test_files with '../' paths must be rejected."""
        inst = _make_instance(
            test_files=(("../../../etc/evil.py", "malicious content"),),
        )
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            with pytest.raises(ValueError, match="Path traversal"):
                write_test_infrastructure(ws, inst)

    def test_absolute_path_blocked(self):
        """test_files with absolute paths must be rejected."""
        inst = _make_instance(
            test_files=(("/tmp/evil.py", "malicious content"),),
        )
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            with pytest.raises(ValueError, match="Path traversal"):
                write_test_infrastructure(ws, inst)


# ── Runner: _parse_test_results ────────────────────────────────────────


class TestParseTestResults:

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            data = {"test_a": True, "test_b": False}
            (ws / "results.json").write_text(json.dumps(data))
            assert _parse_test_results(ws, "results.json") == data

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            assert _parse_test_results(Path(d), "results.json") is None

    def test_corrupt_json(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "results.json").write_text("not json{")
            assert _parse_test_results(ws, "results.json") is None

    def test_non_dict_json(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "results.json").write_text("[1, 2, 3]")
            assert _parse_test_results(ws, "results.json") is None


# ── Runner: evaluate_instance ──────────────────────────────────────────


class TestEvaluateInstance:

    def _setup_results(self, ws: Path, pr_results: dict | None, repo_results: dict | None):
        """Write test result files that the evaluator will parse."""
        if pr_results is not None:
            (ws / "pr_test_results.json").write_text(json.dumps(pr_results))
        if repo_results is not None:
            (ws / "test_results.json").write_text(json.dumps(repo_results))

    @patch("lib.agentbench_runner.run_in_docker")
    def test_all_pass(self, mock_docker):
        inst = _make_instance(
            repo_test_after_pr_patch={"test_a": True, "test_b": True},
        )
        mock_docker.return_value = MagicMock(exit_code=0)

        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            # Pre-write both result files (evaluator reads after Docker returns)
            self._setup_results(ws, {"t1": True, "t2": True}, {"test_a": True, "test_b": True})

            success, output = evaluate_instance(ws, inst, "test-image")
            assert success is True
            assert "INSTANCE: 2/2 passed" in output
            assert "REGRESSION: 2/2 passed" in output

    @patch("lib.agentbench_runner.run_in_docker")
    def test_instance_test_fails(self, mock_docker):
        inst = _make_instance()
        mock_docker.return_value = MagicMock(exit_code=1)

        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            self._setup_results(ws, {"t1": True, "t2": False}, None)

            success, output = evaluate_instance(ws, inst, "test-image")
            assert success is False
            assert "INSTANCE: 1/2 passed" in output

    @patch("lib.agentbench_runner.run_in_docker")
    def test_missing_pr_results(self, mock_docker):
        inst = _make_instance()
        mock_docker.return_value = MagicMock(exit_code=1)

        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            # No result files written
            success, output = evaluate_instance(ws, inst, "test-image")
            assert success is False
            assert "missing or corrupt" in output

    @patch("lib.agentbench_runner.run_in_docker")
    def test_empty_pr_results_not_treated_as_all_pass(self, mock_docker):
        """Empty dict should not be treated as 'all tests passed'."""
        inst = _make_instance()
        mock_docker.return_value = MagicMock(exit_code=0)

        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            # Empty results dict — all({}.values()) is True, but should not count as pass
            self._setup_results(ws, {}, None)

            success, output = evaluate_instance(ws, inst, "test-image")
            assert success is False
            assert "0/0" in output

    @patch("lib.agentbench_runner.run_in_docker")
    def test_regression_flipped_tests(self, mock_docker):
        inst = _make_instance(
            repo_test_after_pr_patch={"test_a": True, "test_b": True},
        )
        mock_docker.return_value = MagicMock(exit_code=0)

        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            # Instance tests pass, but regression test_b flipped from True -> False
            self._setup_results(
                ws,
                {"t1": True},
                {"test_a": True, "test_b": False},
            )

            success, output = evaluate_instance(ws, inst, "test-image")
            assert success is False
            assert "regressions" in output


# ── Runner: build_prompt ───────────────────────────────────────────────


class TestBuildPrompt:

    def test_none_condition_no_preamble(self):
        prompt = build_prompt("Fix the bug.", Condition.NONE)
        assert "Fix the bug." in prompt
        assert "AGENTS.md" not in prompt
        assert "CLAUDE.md" not in prompt

    def test_flat_llm_has_preamble(self):
        prompt = build_prompt("Fix the bug.", Condition.FLAT_LLM)
        assert "Fix the bug." in prompt
        assert "CLAUDE.md" in prompt

    def test_intent_layer_has_preamble(self):
        prompt = build_prompt("Fix the bug.", Condition.INTENT_LAYER)
        assert "Fix the bug." in prompt
        assert "AGENTS.md" in prompt

    def test_human_condition_has_preamble(self):
        prompt = build_prompt("Fix the bug.", Condition.HUMAN)
        assert "Fix the bug." in prompt
        assert "AGENTS.md" in prompt

    def test_prompt_includes_test_instruction(self):
        prompt = build_prompt("Fix X.", Condition.NONE)
        assert "Do not modify the test files" in prompt
