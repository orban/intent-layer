# tests/test_git_ops.py
import pytest
from pathlib import Path
from lib.git_ops import (
    clone_repo,
    checkout_commit,
    get_commit_message,
    get_diff_stats,
    DiffStats,
    _is_context_file,
)


@pytest.fixture
def temp_clone(tmp_path):
    """Clone a small real repo for testing."""
    # Use a tiny public repo
    repo_path = tmp_path / "repo"
    clone_repo(
        url="https://github.com/octocat/Hello-World.git",
        dest=str(repo_path),
        shallow=True
    )
    return repo_path


def test_clone_repo(tmp_path):
    dest = tmp_path / "cloned"
    clone_repo(
        url="https://github.com/octocat/Hello-World.git",
        dest=str(dest),
        shallow=True
    )
    assert (dest / ".git").exists()


def test_get_diff_stats_structure():
    stats = DiffStats(lines_changed=50, files_changed=3, files=["a.py", "b.py", "c.py"])
    assert stats.lines_changed == 50
    assert stats.files_changed == 3


# --- Context file exclusion tests ---


def test_is_context_file_agents_md():
    """AGENTS.md at any depth should be a context file."""
    assert _is_context_file("AGENTS.md") is True
    assert _is_context_file("src/AGENTS.md") is True
    assert _is_context_file("src/lib/AGENTS.md") is True


def test_is_context_file_claude_md():
    """CLAUDE.md at any depth should be a context file."""
    assert _is_context_file("CLAUDE.md") is True
    assert _is_context_file("docs/CLAUDE.md") is True


def test_is_context_file_github_dir():
    """.github/ directory contents should be context files."""
    assert _is_context_file(".github/workflows/ci.yml") is True
    assert _is_context_file(".github/dependabot.yml") is True


def test_is_context_file_claude_dir():
    """.claude/ directory contents should be context files."""
    assert _is_context_file(".claude/settings.json") is True
    assert _is_context_file(".claude/plugins/test.json") is True


def test_is_context_file_cursor_patterns():
    """.cursor/ and .cursorrules should be context files."""
    assert _is_context_file(".cursor/rules/test.mdc") is True
    assert _is_context_file(".cursorrules") is True


def test_is_context_file_regular_files():
    """Regular source files should NOT be context files."""
    assert _is_context_file("src/main.py") is False
    assert _is_context_file("README.md") is False
    assert _is_context_file("package.json") is False
    assert _is_context_file("lib/agents.py") is False  # lowercase, not AGENTS.md
