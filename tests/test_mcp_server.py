"""Tests for the Intent Layer MCP server.

Tests path validation, tool dispatch, resource listing, and
INTENT_LAYER_ALLOWED_PROJECTS enforcement. Subprocess calls are mocked
so these are pure unit tests.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# We need to set INTENT_LAYER_ALLOWED_PROJECTS before importing the server
# module so that tool calls don't fail during import. We'll override per-test.

# Ensure the import can find the plugin root by patching _find_plugin_root
# if needed. In practice the repo checkout already has .claude-plugin/.

import sys

# Add the mcp/ directory so we can import server
MCP_DIR = str(Path(__file__).resolve().parent.parent / "mcp")
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from server import (
    _find_plugin_root,
    _get_allowed_projects,
    _is_intent_file,
    _validate_path_within_project,
    _validate_project_root,
    PLUGIN_ROOT,
    SUBPROCESS_TIMEOUT,
    read_intent,
    report_learning,
    read_intent_resource,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_project(tmp_path: Path):
    """Create a minimal fake project tree with AGENTS.md files."""
    root = tmp_path / "my-project"
    root.mkdir()
    (root / "CLAUDE.md").write_text("# Root\n")
    src = root / "src"
    src.mkdir()
    (src / "AGENTS.md").write_text("# Src agents\n")
    (src / "app.py").write_text("print('hi')\n")
    subdir = src / "api"
    subdir.mkdir()
    (subdir / "AGENTS.md").write_text("# API agents\n")
    # A non-intent file
    (root / "README.md").write_text("# readme\n")
    return str(root.resolve())


@pytest.fixture(autouse=True)
def _set_allowed_projects(tmp_project: str):
    """Set the allowlist env var for every test."""
    with mock.patch.dict(
        os.environ, {"INTENT_LAYER_ALLOWED_PROJECTS": tmp_project}
    ):
        yield


# ---------------------------------------------------------------------------
# Security: allowlist enforcement
# ---------------------------------------------------------------------------

class TestAllowlistEnforcement:
    def test_missing_env_var_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INTENT_LAYER_ALLOWED_PROJECTS", None)
            with pytest.raises(ValueError, match="not set"):
                _get_allowed_projects()

    def test_project_not_in_allowlist(self, tmp_path: Path):
        with pytest.raises(ValueError, match="not in the allowed projects"):
            _validate_project_root(str(tmp_path / "not-allowed"))

    def test_valid_project_accepted(self, tmp_project: str):
        result = _validate_project_root(tmp_project)
        assert result == os.path.realpath(tmp_project)


# ---------------------------------------------------------------------------
# Security: path traversal
# ---------------------------------------------------------------------------

class TestPathTraversal:
    def test_traversal_via_dotdot_rejected(self, tmp_project: str):
        canonical_root = os.path.realpath(tmp_project)
        with pytest.raises(ValueError, match="outside the project root"):
            _validate_path_within_project(
                canonical_root, os.path.join(canonical_root, "..", "etc", "passwd")
            )

    def test_absolute_escape_rejected(self, tmp_project: str):
        canonical_root = os.path.realpath(tmp_project)
        with pytest.raises(ValueError, match="outside the project root"):
            _validate_path_within_project(canonical_root, "/etc/passwd")

    def test_path_within_project_accepted(self, tmp_project: str):
        canonical_root = os.path.realpath(tmp_project)
        target = os.path.join(canonical_root, "src", "app.py")
        result = _validate_path_within_project(canonical_root, target)
        assert result == os.path.realpath(target)

    def test_project_root_itself_accepted(self, tmp_project: str):
        canonical_root = os.path.realpath(tmp_project)
        result = _validate_path_within_project(canonical_root, canonical_root)
        assert result == canonical_root

    def test_symlink_resolved(self, tmp_project: str):
        """Symlinks are resolved before checking containment."""
        canonical_root = os.path.realpath(tmp_project)
        link = os.path.join(canonical_root, "link_to_outside")
        # Create a symlink pointing outside the project
        os.symlink("/tmp", link)
        try:
            with pytest.raises(ValueError, match="outside the project root"):
                _validate_path_within_project(canonical_root, link)
        finally:
            os.unlink(link)


# ---------------------------------------------------------------------------
# Tool: read_intent
# ---------------------------------------------------------------------------

class TestReadIntent:
    @mock.patch("server.subprocess.run")
    def test_success(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="# Context output\n", stderr=""
        )
        result = read_intent(tmp_project, "src/api/")
        assert "Context output" in result
        # Verify the script was called with canonical paths
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0].endswith("resolve_context.sh")
        assert os.path.realpath(tmp_project) in cmd[1]

    @mock.patch("server.subprocess.run")
    def test_with_sections_filter(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="filtered\n", stderr=""
        )
        read_intent(tmp_project, "src/", sections="Contracts,Pitfalls")
        cmd = mock_run.call_args[0][0]
        assert "--sections" in cmd
        idx = cmd.index("--sections")
        assert cmd[idx + 1] == "Contracts,Pitfalls"

    @mock.patch("server.subprocess.run")
    def test_no_coverage_returns_message(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr=""
        )
        result = read_intent(tmp_project, "src/")
        assert "No Intent Layer coverage" in result

    @mock.patch("server.subprocess.run")
    def test_script_error_raises(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="bad args"
        )
        with pytest.raises(ValueError, match="bad args"):
            read_intent(tmp_project, "src/")

    @mock.patch("server.subprocess.run")
    def test_timeout_raises(self, mock_run, tmp_project: str):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=30)
        with pytest.raises(RuntimeError, match="timed out"):
            read_intent(tmp_project, "src/")

    def test_traversal_rejected(self, tmp_project: str):
        with pytest.raises(ValueError, match="outside the project root"):
            read_intent(tmp_project, "../../etc/passwd")

    def test_disallowed_project_rejected(self):
        with pytest.raises(ValueError, match="not in the allowed"):
            read_intent("/not/allowed/project", "src/")

    def test_missing_allowlist_rejected(self, tmp_project: str):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("INTENT_LAYER_ALLOWED_PROJECTS", None)
            with pytest.raises(ValueError, match="not set"):
                read_intent(tmp_project, "src/")


# ---------------------------------------------------------------------------
# Tool: report_learning
# ---------------------------------------------------------------------------

class TestReportLearning:
    @mock.patch("server.subprocess.run")
    def test_success(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Created report-12345.md", stderr=""
        )
        result = report_learning(
            project_root=tmp_project,
            path="src/api/",
            type="pitfall",
            title="Test pitfall",
            detail="Something broke",
        )
        assert "successfully" in result
        cmd = mock_run.call_args[0][0]
        assert cmd[0].endswith("report_learning.sh")
        assert "--type" in cmd
        assert "pitfall" in cmd

    @mock.patch("server.subprocess.run")
    def test_with_agent_id(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr=""
        )
        report_learning(
            project_root=tmp_project,
            path="src/",
            type="insight",
            title="A title",
            detail="Details here",
            agent_id="worker-7",
        )
        cmd = mock_run.call_args[0][0]
        assert "--agent-id" in cmd
        idx = cmd.index("--agent-id")
        assert cmd[idx + 1] == "worker-7"

    @mock.patch("server.subprocess.run")
    def test_script_failure_raises(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Missing --type"
        )
        with pytest.raises(ValueError, match="Missing --type"):
            report_learning(
                project_root=tmp_project,
                path="src/",
                type="pitfall",
                title="x",
                detail="y",
            )

    @mock.patch("server.subprocess.run")
    def test_timeout_raises(self, mock_run, tmp_project: str):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=30)
        with pytest.raises(RuntimeError, match="timed out"):
            report_learning(
                project_root=tmp_project,
                path="src/",
                type="pitfall",
                title="x",
                detail="y",
            )

    def test_traversal_rejected(self, tmp_project: str):
        with pytest.raises(ValueError, match="outside the project root"):
            report_learning(
                project_root=tmp_project,
                path="../../../etc/shadow",
                type="pitfall",
                title="x",
                detail="y",
            )

    @mock.patch("server.subprocess.run")
    def test_env_includes_plugin_root(self, mock_run, tmp_project: str):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr=""
        )
        report_learning(
            project_root=tmp_project,
            path="src/",
            type="check",
            title="t",
            detail="d",
        )
        env = mock_run.call_args[1].get("env") or mock_run.call_args.kwargs.get("env")
        assert env is not None
        assert env["CLAUDE_PLUGIN_ROOT"] == PLUGIN_ROOT


# ---------------------------------------------------------------------------
# Resource: intent:// files
# ---------------------------------------------------------------------------

class TestIntentResource:
    def test_read_claude_md(self, tmp_project: str):
        project_name = os.path.basename(tmp_project)
        content = read_intent_resource(project_name, "CLAUDE.md")
        assert "# Root" in content

    def test_read_agents_md(self, tmp_project: str):
        project_name = os.path.basename(tmp_project)
        content = read_intent_resource(project_name, "src/AGENTS.md")
        assert "# Src agents" in content

    def test_non_intent_file_rejected(self, tmp_project: str):
        project_name = os.path.basename(tmp_project)
        with pytest.raises(ValueError, match="limited to AGENTS.md and CLAUDE.md"):
            read_intent_resource(project_name, "README.md")

    def test_unknown_project_rejected(self, tmp_project: str):
        with pytest.raises(ValueError, match="not found in allowed"):
            read_intent_resource("nonexistent-project", "CLAUDE.md")

    def test_traversal_rejected(self, tmp_project: str):
        project_name = os.path.basename(tmp_project)
        with pytest.raises(ValueError, match="outside the project root"):
            read_intent_resource(project_name, "../../etc/passwd")

    def test_missing_file_rejected(self, tmp_project: str):
        project_name = os.path.basename(tmp_project)
        with pytest.raises(ValueError, match="File not found"):
            read_intent_resource(project_name, "nonexistent/AGENTS.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_is_intent_file_agents(self):
        assert _is_intent_file("/some/path/AGENTS.md") is True

    def test_is_intent_file_claude(self):
        assert _is_intent_file("/project/CLAUDE.md") is True

    def test_is_intent_file_other(self):
        assert _is_intent_file("/project/README.md") is False
        assert _is_intent_file("/project/agents.md") is False

    def test_find_plugin_root_returns_repo(self):
        # The test runs from within the repo, so this should work
        assert os.path.isdir(os.path.join(PLUGIN_ROOT, ".claude-plugin"))

    def test_subprocess_timeout_value(self):
        assert SUBPROCESS_TIMEOUT == 30
