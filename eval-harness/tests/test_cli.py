# tests/test_cli.py
import pytest
from click.testing import CliRunner
from lib.cli import main, scan, run


@pytest.fixture
def runner():
    return CliRunner()


def test_main_shows_help(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "A/B eval harness" in result.output or "evaluation framework" in result.output


def test_scan_shows_help(runner):
    result = runner.invoke(scan, ["--help"])
    assert result.exit_code == 0
    assert "--repo" in result.output


def test_run_shows_help(runner):
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert "--tasks" in result.output
    # The current stub has --parallel, so this might pass
    assert "--parallel" in result.output


def test_run_validates_tasks_exist(runner, tmp_path):
    result = runner.invoke(run, ["--tasks", str(tmp_path / "nonexistent.yaml")])
    # The current stub does NOT validate existence, so this should fail
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()
