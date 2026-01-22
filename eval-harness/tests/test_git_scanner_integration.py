# tests/test_git_scanner_integration.py
import pytest
import subprocess
from pathlib import Path
from lib.git_scanner import GitScanner

def setup_git_repo(path: Path):
    """Initialize a git repo with some history."""
    # Init
    subprocess.run(["git", "init"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)

    # Initial commit
    (path / "main.py").write_text("def foo():\n    return None\n")
    (path / "test_main.py").write_text("def test_foo():\n    assert True\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=path, check=True)

    # Feature commit (should be ignored)
    (path / "feature.py").write_text("print('feature')")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add feature"], cwd=path, check=True)

    # Bug fix commit 1: Simple fix
    (path / "main.py").write_text("def foo():\n    return 'bar'\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "fix: return correct value"], cwd=path, check=True)

    # Bug fix commit 2: With failing test
    (path / "test_main.py").write_text("import main\ndef test_foo():\n    assert main.foo() == 'bar'\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "fix: update test to match implementation"], cwd=path, check=True)

def test_scan_local_repo(tmp_path):
    """Test verification that the scanner works on a real (local) git repo."""
    setup_git_repo(tmp_path)

    scanner = GitScanner()
    tasks = scanner.scan_repo(str(tmp_path))

    assert len(tasks) == 2
    
    # Check most recent fix
    task1 = tasks[0]
    assert "fix: update test" in task1.commit_message
    assert task1.files_changed == 1
    assert task1.test_file == "test_main.py"

    # Check previous fix
    task2 = tasks[1]
    assert "fix: return correct value" in task2.commit_message
    assert task2.files_changed == 1
    assert task2.test_file is None
