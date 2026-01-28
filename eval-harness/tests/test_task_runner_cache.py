# tests/test_task_runner_cache.py
import tempfile
from pathlib import Path
from lib.task_runner import TaskRunner, SkillGenerationMetrics
from lib.index_cache import IndexCache
from lib.models import RepoConfig, DockerConfig


def test_cache_hit_restores_files():
    """Test that cache hit restores AGENTS.md files without running Claude."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / ".index-cache"
        workspace_base = Path(tmpdir) / "workspaces"

        # Pre-populate cache
        cache = IndexCache(str(cache_dir))
        with tempfile.TemporaryDirectory() as mock_workspace:
            mock_ws_path = Path(mock_workspace)
            (mock_ws_path / "CLAUDE.md").write_text("# Cached Root")
            (mock_ws_path / "src").mkdir()
            (mock_ws_path / "src" / "AGENTS.md").write_text("# Cached Src")

            cache.save(
                "https://github.com/user/repo",
                "abc123456789",
                mock_workspace,
                ["CLAUDE.md", "src/AGENTS.md"]
            )

        # Create minimal repo config
        repo_config = RepoConfig(
            url="https://github.com/user/repo",
            docker=DockerConfig(
                image="python:3.9",
                setup=[],
                test_command="pytest"
            )
        )

        # Create TaskRunner
        runner = TaskRunner(
            repo=repo_config,
            workspaces_dir=str(workspace_base),
            cache_dir=str(cache_dir),
            use_cache=True
        )

        # Create test workspace
        test_workspace = workspace_base / "test-workspace"
        test_workspace.mkdir(parents=True)

        # Call _check_or_generate_index (we'll create this helper method)
        metrics = runner._check_or_generate_index(
            workspace=str(test_workspace),
            repo_url="https://github.com/user/repo",
            commit="abc123456789"
        )

        # Verify cache hit
        assert metrics.cache_hit is True
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
        assert metrics.wall_clock_seconds < 1.0  # Should be fast

        # Verify files were restored
        assert (test_workspace / "CLAUDE.md").exists()
        assert (test_workspace / "src" / "AGENTS.md").exists()
        assert (test_workspace / "CLAUDE.md").read_text() == "# Cached Root"


def test_cache_miss_generates_and_saves():
    """Test that cache miss generates index and saves to cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / ".index-cache"
        workspace_base = Path(tmpdir) / "workspaces"

        # Create minimal repo config
        repo_config = RepoConfig(
            url="https://github.com/user/new-repo",
            docker=DockerConfig(
                image="python:3.9",
                setup=[],
                test_command="pytest"
            )
        )

        # Create TaskRunner with empty cache
        runner = TaskRunner(
            repo=repo_config,
            workspaces_dir=str(workspace_base),
            cache_dir=str(cache_dir),
            use_cache=True
        )

        # Create test workspace with mock files
        test_workspace = workspace_base / "test-workspace"
        test_workspace.mkdir(parents=True)
        (test_workspace / "README.md").write_text("# Test")

        # Mock the skill generation to create AGENTS.md files
        # (In real implementation, this would call run_claude)
        # For now, we'll manually create files to simulate generation
        (test_workspace / "CLAUDE.md").write_text("# Generated Root")

        # Verify cache is initially empty
        entry = runner.index_cache.lookup("https://github.com/user/new-repo", "def456")
        assert entry is None

        # This test will fail until we implement _check_or_generate_index
        # For now, we'll mark this as a placeholder
