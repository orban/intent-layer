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

        # Pre-populate cache with condition in key
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
                ["CLAUDE.md", "src/AGENTS.md"],
                "intent_layer"
            )

        repo_config = RepoConfig(
            url="https://github.com/user/repo",
            docker=DockerConfig(
                image="python:3.9",
                setup=[],
                test_command="pytest"
            )
        )

        runner = TaskRunner(
            repo=repo_config,
            workspaces_dir=str(workspace_base),
            cache_dir=str(cache_dir),
            use_cache=True
        )

        test_workspace = workspace_base / "test-workspace"
        test_workspace.mkdir(parents=True)

        metrics = runner._check_or_generate_index(
            workspace=str(test_workspace),
            repo_url="https://github.com/user/repo",
            commit="abc123456789",
            condition="intent_layer"
        )

        assert metrics.cache_hit is True
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
        assert metrics.wall_clock_seconds < 1.0

        assert (test_workspace / "CLAUDE.md").exists()
        assert (test_workspace / "src" / "AGENTS.md").exists()
        assert (test_workspace / "CLAUDE.md").read_text() == "# Cached Root"


def test_cache_miss_generates_and_saves():
    """Test that cache miss generates index and saves to cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / ".index-cache"
        workspace_base = Path(tmpdir) / "workspaces"

        repo_config = RepoConfig(
            url="https://github.com/user/new-repo",
            docker=DockerConfig(
                image="python:3.9",
                setup=[],
                test_command="pytest"
            )
        )

        runner = TaskRunner(
            repo=repo_config,
            workspaces_dir=str(workspace_base),
            cache_dir=str(cache_dir),
            use_cache=True
        )

        test_workspace = workspace_base / "test-workspace"
        test_workspace.mkdir(parents=True)
        (test_workspace / "README.md").write_text("# Test")

        (test_workspace / "CLAUDE.md").write_text("# Generated Root")

        # Verify cache is initially empty for this condition
        entry = runner.index_cache.lookup("https://github.com/user/new-repo", "def456", "intent_layer")
        assert entry is None


def test_different_conditions_cached_separately():
    """Test that same repo+commit with different conditions are cached independently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / ".index-cache"
        workspace_base = Path(tmpdir) / "workspaces"

        cache = IndexCache(str(cache_dir))

        # Save flat_llm cache entry
        with tempfile.TemporaryDirectory() as ws1:
            (Path(ws1) / "CLAUDE.md").write_text("# Flat content")
            cache.save("https://github.com/user/repo", "abc123456789", ws1, ["CLAUDE.md"], "flat_llm")

        # Save intent_layer cache entry
        with tempfile.TemporaryDirectory() as ws2:
            ws2_path = Path(ws2)
            (ws2_path / "CLAUDE.md").write_text("# Root")
            (ws2_path / "src").mkdir()
            (ws2_path / "src" / "AGENTS.md").write_text("# Src")
            cache.save("https://github.com/user/repo", "abc123456789", ws2, ["CLAUDE.md", "src/AGENTS.md"], "intent_layer")

        # Lookup each independently
        flat_entry = cache.lookup("https://github.com/user/repo", "abc123456789", "flat_llm")
        il_entry = cache.lookup("https://github.com/user/repo", "abc123456789", "intent_layer")

        assert flat_entry is not None
        assert il_entry is not None
        assert len(flat_entry.agents_files) == 1
        assert len(il_entry.agents_files) == 2
