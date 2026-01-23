# tests/test_git_scanner.py
import pytest
from lib.git_scanner import GitScanner, ScannedTask


def test_scanned_task_structure():
    task = ScannedTask(
        id="fix-null-check",
        category="simple_fix",
        pre_fix_commit="abc123",
        fix_commit="def456",
        commit_message="fix: handle null in parser",
        lines_changed=15,
        files_changed=1,
        test_file="test/parser.test.js"
    )
    assert task.category == "simple_fix"


def test_categorize_by_size():
    scanner = GitScanner()

    assert scanner.categorize(lines=10, files=1) == "simple_fix"
    assert scanner.categorize(lines=100, files=4) == "targeted_refactor"
    assert scanner.categorize(lines=300, files=10) == "complex_fix"


def test_is_bug_fix_commit():
    scanner = GitScanner()

    assert scanner.is_bug_fix("fix: null pointer exception")
    assert scanner.is_bug_fix("bug: handle edge case")
    assert scanner.is_bug_fix("Fixes #123")
    assert not scanner.is_bug_fix("feat: add new feature")
    assert not scanner.is_bug_fix("docs: update readme")
