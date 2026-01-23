# tests/test_integration.py
"""
Integration test that runs the full pipeline on a mock repo.
Skipped by default - run with: pytest -m integration
"""
import pytest
from pathlib import Path
from click.testing import CliRunner

from lib.cli import main


@pytest.mark.integration
@pytest.mark.skip(reason="Requires Docker and Claude CLI - run manually")
def test_full_pipeline(tmp_path):
    """Full integration test with a real repo."""
    runner = CliRunner()

    # Step 1: Scan a small real repo
    task_file = tmp_path / "tasks.yaml"
    result = runner.invoke(main, [
        "scan",
        "--repo", "https://github.com/octocat/Hello-World.git",
        "--output", str(task_file),
        "--limit", "2"
    ])

    assert result.exit_code == 0
    assert task_file.exists()

    # Step 2: Verify task file is valid YAML
    from lib.models import TaskFile
    task_data = TaskFile.from_yaml(task_file)
    assert len(task_data.tasks) <= 2
