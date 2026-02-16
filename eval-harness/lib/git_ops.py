# lib/git_ops.py
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class DiffStats:
    lines_changed: int
    files_changed: int
    files: list[str]


def clone_repo(url: str, dest: str, shallow: bool = True) -> None:
    """Clone a repository."""
    cmd = ["git", "clone"]
    if shallow:
        cmd.extend(["--depth", "1"])
    cmd.extend([url, dest])
    subprocess.run(cmd, check=True, capture_output=True)


def checkout_commit(repo_path: str, commit: str) -> None:
    """Checkout a specific commit. Fetches if needed."""
    # First try direct checkout
    result = subprocess.run(
        ["git", "checkout", commit],
        cwd=repo_path,
        capture_output=True
    )
    if result.returncode != 0:
        # Fetch the commit and retry
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", commit],
            cwd=repo_path,
            check=True,
            capture_output=True
        )
        subprocess.run(
            ["git", "checkout", commit],
            cwd=repo_path,
            check=True,
            capture_output=True
        )


def get_commit_message(repo_path: str, commit: str) -> str:
    """Get the commit message for a given commit."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%B", commit],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def create_baseline_commit(repo_path: str) -> None:
    """Stage and commit all current changes as a baseline.

    Called after strip + context generation so that get_diff_stats
    only measures changes made by Claude, not by the harness itself.
    """
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_path,
        check=True,
        capture_output=True
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "eval-harness baseline"],
        cwd=repo_path,
        capture_output=True  # don't check — nothing to commit is fine
    )


def get_diff_stats(repo_path: str) -> DiffStats:
    """Get diff stats for uncommitted changes (tracked + untracked).

    Stages all changes first so new files created by Claude are included.
    """
    # Stage everything so untracked files show up in the diff
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_path,
        capture_output=True
    )

    # Get list of changed files (staged vs HEAD)
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    files = [f for f in result.stdout.strip().split("\n") if f]

    # Get line counts (staged vs HEAD)
    result = subprocess.run(
        ["git", "diff", "--cached", "--shortstat", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )

    lines_changed = 0
    stat_output = result.stdout.strip()
    # Parse "X files changed, Y insertions(+), Z deletions(-)"
    matches = re.findall(r"(\d+) insertion|(\d+) deletion", stat_output)
    for ins, dels in matches:
        if ins:
            lines_changed += int(ins)
        if dels:
            lines_changed += int(dels)

    return DiffStats(
        lines_changed=lines_changed,
        files_changed=len(files),
        files=files
    )
