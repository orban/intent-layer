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
    assert "A/B/C eval harness" in result.output or "eval harness" in result.output


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


def test_run_accepts_condition_flag(runner):
    """Test that run command accepts --condition flag with valid values."""
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert "--condition" in result.output

    # Valid condition values should parse (fail on missing task file, not flag parsing)
    result = runner.invoke(run, ["--tasks", "dummy.yaml", "--condition", "none", "--dry-run"])
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    result = runner.invoke(run, ["--tasks", "dummy.yaml", "-c", "flat_llm", "-c", "intent_layer", "--dry-run"])
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    # Invalid condition value should be rejected by click.Choice
    result = runner.invoke(run, ["--tasks", "dummy.yaml", "--condition", "bogus"])
    assert result.exit_code != 0


def test_run_accepts_model_flag(runner):
    """Test that run command accepts --model flag."""
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert "--model" in result.output

    # Model flag should parse (fail on missing task file, not flag parsing)
    result = runner.invoke(run, ["--tasks", "dummy.yaml", "--model", "claude-sonnet-4-5-20250929", "--dry-run"])
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()


def test_run_accepts_cache_flags(runner):
    """Test that run command accepts cache management flags."""
    # Test --help includes cache flags
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert "--clear-cache" in result.output
    assert "--no-cache" in result.output
    assert "--cache-dir" in result.output

    # Test flags parse without errors (will fail on missing tasks, but flags should parse)
    result = runner.invoke(run, ["--tasks", "dummy.yaml", "--clear-cache", "--dry-run"])
    # Should fail on missing file, not on flag parsing
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    result = runner.invoke(run, ["--tasks", "dummy.yaml", "--no-cache", "--dry-run"])
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    result = runner.invoke(run, ["--tasks", "dummy.yaml", "--cache-dir", "/tmp/cache", "--dry-run"])
    assert "does not exist" in result.output.lower() or "error" in result.output.lower()


def test_run_clear_cache_integration(runner, tmp_path):
    """Test that --clear-cache actually clears the cache."""
    from lib.index_cache import IndexCache

    # Set up a custom cache dir
    cache_dir = tmp_path / "test-cache"
    cache_dir.mkdir()

    # Create a dummy workspace with AGENTS.md file
    dummy_workspace = tmp_path / "dummy-workspace"
    dummy_workspace.mkdir()
    (dummy_workspace / "AGENTS.md").write_text("# Test")

    # Create a cache with some entries
    cache = IndexCache(str(cache_dir))
    cache.save("https://example.com/repo", "abc123def", str(dummy_workspace), ["AGENTS.md"])

    # Verify cache has entries (should have manifest + entry directory)
    cache_contents = list(cache_dir.iterdir())
    assert len(cache_contents) > 1  # manifest + at least one cache entry

    # Create a minimal task file for dry-run
    task_file = tmp_path / "tasks.yaml"
    task_file.write_text("""repo:
  url: https://example.com/repo
  default_branch: main
  docker:
    image: node:20-slim
    setup: []
    test_command: npm test
tasks: []
""")

    # Run with --clear-cache and --dry-run
    result = runner.invoke(run, [
        "--tasks", str(task_file),
        "--cache-dir", str(cache_dir),
        "--clear-cache",
        "--dry-run"
    ])

    assert result.exit_code == 0
    assert "Cleared index cache" in result.output

    # Verify cache was cleared (only manifest.json should remain)
    cache_contents = list(cache_dir.iterdir())
    # Should only have manifest, and manifest should be empty
    assert len(cache_contents) == 1
    assert cache_contents[0].name == "cache-manifest.json"
