# lib/git_scanner.py
from __future__ import annotations
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ScannedTask:
    id: str
    category: str
    pre_fix_commit: str
    fix_commit: str
    commit_message: str
    lines_changed: int
    files_changed: int
    test_file: str | None = None
    issue_number: int | None = None


class GitScanner:
    BUG_FIX_PATTERNS = [
        r'\bfix\b',
        r'\bbug\b',
        r'\bfixes?\s+#\d+',
        r'\bcloses?\s+#\d+',
        r'\bresolves?\s+#\d+',
    ]

    def __init__(self):
        self.bug_fix_re = re.compile(
            '|'.join(self.BUG_FIX_PATTERNS),
            re.IGNORECASE
        )

    def is_bug_fix(self, message: str) -> bool:
        """Check if commit message indicates a bug fix."""
        return bool(self.bug_fix_re.search(message))

    def categorize(self, lines: int, files: int) -> str:
        """Categorize by size."""
        if lines < 50 and files <= 2:
            return "simple_fix"
        elif lines < 200 and files <= 5:
            return "targeted_refactor"
        else:
            return "complex_fix"

    def scan_repo(
        self,
        repo_path: str,
        since: str | None = None,
        limit: int = 50
    ) -> list[ScannedTask]:
        """Scan a repo for bug fix commits."""
        cmd = ["git", "log", "--format=%H|%s", f"-{limit * 10}"]  # Over-fetch
        if since:
            cmd.append(f"--since={since}")

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )

        tasks = []
        for line in result.stdout.strip().split("\n"):
            if not line or "|" not in line:
                continue

            commit_hash, message = line.split("|", 1)

            if not self.is_bug_fix(message):
                continue

            # Get parent commit
            parent_result = subprocess.run(
                ["git", "rev-parse", f"{commit_hash}^"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if parent_result.returncode != 0:
                continue
            parent = parent_result.stdout.strip()

            # Get diff stats
            stats = self._get_commit_stats(repo_path, commit_hash)

            # Find test file in diff
            test_file = self._find_test_file(repo_path, commit_hash)

            # Extract issue number
            issue_match = re.search(r'#(\d+)', message)
            issue_number = int(issue_match.group(1)) if issue_match else None

            task = ScannedTask(
                id=self._slugify(message[:50]),
                category=self.categorize(stats["lines"], stats["files"]),
                pre_fix_commit=parent,
                fix_commit=commit_hash,
                commit_message=message,
                lines_changed=stats["lines"],
                files_changed=stats["files"],
                test_file=test_file,
                issue_number=issue_number
            )
            tasks.append(task)

            if len(tasks) >= limit:
                break

        return tasks

    def _get_commit_stats(self, repo_path: str, commit: str) -> dict:
        """Get lines and files changed for a commit."""
        result = subprocess.run(
            ["git", "diff", "--shortstat", f"{commit}^", commit],
            cwd=repo_path,
            capture_output=True,
            text=True
        )

        output = result.stdout.strip()
        lines = 0
        files = 0

        file_match = re.search(r'(\d+) files? changed', output)
        if file_match:
            files = int(file_match.group(1))

        ins_match = re.search(r'(\d+) insertions?', output)
        del_match = re.search(r'(\d+) deletions?', output)
        if ins_match:
            lines += int(ins_match.group(1))
        if del_match:
            lines += int(del_match.group(1))

        return {"lines": lines, "files": files}

    def _find_test_file(self, repo_path: str, commit: str) -> str | None:
        """Find test file in commit diff."""
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{commit}^", commit],
            cwd=repo_path,
            capture_output=True,
            text=True
        )

        for file in result.stdout.strip().split("\n"):
            if re.search(r'test|spec', file, re.IGNORECASE):
                return file

        return None

    def _slugify(self, text: str) -> str:
        """Convert text to slug."""
        text = re.sub(r'[^\w\s-]', '', text.lower())
        return re.sub(r'[-\s]+', '-', text).strip('-')[:50]

    def generate_yaml(
        self,
        tasks: list[ScannedTask],
        repo_url: str,
        docker_image: str,
        setup: list[str],
        test_command: str,
        default_branch: str = "main"
    ) -> str:
        """Generate YAML task file from scanned tasks."""
        data = {
            "repo": {
                "url": repo_url,
                "default_branch": default_branch,
                "docker": {
                    "image": docker_image,
                    "setup": setup,
                    "test_command": test_command
                }
            },
            "tasks": []
        }

        for task in tasks:
            task_data = {
                "id": task.id,
                "category": task.category,
                "pre_fix_commit": task.pre_fix_commit,
                "fix_commit": task.fix_commit,
                "prompt_source": "failing_test" if task.test_file else "commit_message",
                "_commit_message": task.commit_message,
                "_lines_changed": task.lines_changed,
                "_files_changed": task.files_changed,
            }
            if task.test_file:
                task_data["test_file"] = task.test_file
            if task.issue_number:
                task_data["issue_number"] = task.issue_number

            data["tasks"].append(task_data)

        header = f"""# DRAFT - Review and curate before use
# Generated from: {repo_url}
# Tasks found: {len(tasks)}

"""
        return header + yaml.dump(data, sort_keys=False, default_flow_style=False)
