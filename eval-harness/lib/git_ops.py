# lib/git_ops.py
from __future__ import annotations
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
import re

logger = logging.getLogger(__name__)


@dataclass
class DiffStats:
    lines_changed: int
    files_changed: int
    files: list[str]


def clone_repo(url: str, dest: str, shallow: bool = True, reference: str | None = None) -> None:
    """Clone a repository.

    If reference is provided, tries --shared first (git alternates,
    nearly instant) then falls back to --local (hardlink copy) if
    --shared fails. Large repos like transformers and wagtail can
    fail with --shared under concurrent access.
    """
    if reference:
        cmd = ["git", "clone", "--shared", "--no-checkout", reference, dest]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            logger.warning(
                "git clone --shared failed for %s, falling back to --local", dest
            )
            if Path(dest).exists():
                shutil.rmtree(dest)
            cmd = ["git", "clone", "--local", "--no-checkout", reference, dest]
            subprocess.run(cmd, check=True, capture_output=True)
    else:
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

    Disables GPG/SSH signing to avoid failures from global git config
    (e.g., 1Password SSH signing).
    """
    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_path,
        check=True,
        capture_output=True
    )
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit",
         "--allow-empty", "-m", "eval-harness baseline"],
        cwd=repo_path,
        capture_output=True  # don't check — nothing to commit is fine
    )


_CONTEXT_FILE_PATTERNS = re.compile(
    r"(^|/)("
    r"AGENTS\.md|CLAUDE\.md|\.github/|\.claude/|\.cursor/|\.cursorrules"
    r")"
)


def _is_context_file(path: str) -> bool:
    """Return True if path is an AI context file that shouldn't count in diffs."""
    return bool(_CONTEXT_FILE_PATTERNS.search(path))


def get_diff_stats(repo_path: str) -> DiffStats:
    """Get diff stats for uncommitted changes (tracked + untracked).

    Stages all changes first so new files created by Claude are included.
    Excludes AGENTS.md, CLAUDE.md, .github/, .claude/, .cursor/ from counts
    since these are harness artifacts, not agent work product.
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
    all_files = [f for f in result.stdout.strip().split("\n") if f]
    files = [f for f in all_files if not _is_context_file(f)]

    # Get per-file line counts, excluding context files
    lines_changed = 0
    if files:
        result = subprocess.run(
            ["git", "diff", "--cached", "--numstat", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added, deleted, filepath = parts[0], parts[1], parts[2]
            if _is_context_file(filepath):
                continue
            # Binary files show "-" for added/deleted
            if added != "-":
                lines_changed += int(added)
            if deleted != "-":
                lines_changed += int(deleted)

    return DiffStats(
        lines_changed=lines_changed,
        files_changed=len(files),
        files=files
    )
