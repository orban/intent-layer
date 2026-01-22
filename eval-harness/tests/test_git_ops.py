# tests/test_git_ops.py
import pytest
from pathlib import Path
from lib.git_ops import (
    clone_repo,
    checkout_commit,
    get_commit_message,
    get_diff_stats,
    DiffStats
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
