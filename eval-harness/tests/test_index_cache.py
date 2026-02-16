# tests/test_index_cache.py
from pathlib import Path
import json
import tempfile
import shutil
import pytest
from lib.index_cache import IndexCache, CacheEntry


def test_index_cache_creates_manifest():
    """Test that IndexCache creates manifest on init if missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)
        manifest_path = Path(tmpdir) / "cache-manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            data = json.load(f)
            assert data == {"entries": {}}


def test_index_cache_loads_existing_manifest():
    """Test that IndexCache loads existing manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "cache-manifest.json"
        manifest_path.write_text(json.dumps({
            "entries": {
                "repo1-abc12345": {
                    "repo": "repo1",
                    "commit": "abc123456789",
                    "workspace_path": "/tmp/cached",
                    "created_at": "2026-01-23T10:00:00Z",
                    "agents_files": ["CLAUDE.md"]
                }
            }
        }))

        cache = IndexCache(tmpdir)
        assert len(cache.manifest.entries) == 1
        assert "repo1-abc12345" in cache.manifest.entries


def test_get_cache_key():
    """Test cache key generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)
        key = cache.get_cache_key("https://github.com/user/repo", "abc123456789")
        assert key == "repo-abc12345"


def test_lookup_miss():
    """Test cache lookup when entry doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)
        result = cache.lookup("https://github.com/user/repo", "abc123")
        assert result is None


def test_lookup_hit():
    """Test cache lookup when entry exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Pre-populate manifest
        manifest_path = Path(tmpdir) / "cache-manifest.json"
        manifest_path.write_text(json.dumps({
            "entries": {
                "repo-abc12345": {
                    "repo": "https://github.com/user/repo",
                    "commit": "abc123456789",
                    "workspace_path": str(Path(tmpdir) / "repo-abc12345"),
                    "created_at": "2026-01-23T10:00:00Z",
                    "agents_files": ["CLAUDE.md"]
                }
            }
        }))

        cache = IndexCache(tmpdir)
        result = cache.lookup("https://github.com/user/repo", "abc123456789")
        assert result is not None
        assert result.repo == "https://github.com/user/repo"
        assert result.commit == "abc123456789"


def test_save_and_restore():
    """Test saving and restoring index files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)

        # Create a mock workspace with AGENTS.md
        with tempfile.TemporaryDirectory() as workspace:
            workspace_path = Path(workspace)
            (workspace_path / "CLAUDE.md").write_text("# Root")
            (workspace_path / "src").mkdir()
            (workspace_path / "src" / "AGENTS.md").write_text("# Src")

            # Save to cache
            cache.save(
                "https://github.com/user/repo",
                "abc123456789",
                workspace,
                ["CLAUDE.md", "src/AGENTS.md"]
            )

            # Verify cache entry exists
            entry = cache.lookup("https://github.com/user/repo", "abc123456789")
            assert entry is not None
            assert len(entry.agents_files) == 2

            # Restore to new workspace
            with tempfile.TemporaryDirectory() as target:
                cache.restore(entry, target)
                target_path = Path(target)
                assert (target_path / "CLAUDE.md").exists()
                assert (target_path / "src" / "AGENTS.md").exists()
                assert (target_path / "CLAUDE.md").read_text() == "# Root"
                assert (target_path / "src" / "AGENTS.md").read_text() == "# Src"


def test_get_cache_key_with_condition():
    """Test cache key includes condition."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)
        key = cache.get_cache_key("https://github.com/user/repo", "abc123456789", "flat_llm")
        assert key == "repo-abc12345-flat_llm"


def test_get_cache_key_without_condition():
    """Test backward compat: no condition gives old-style key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)
        key = cache.get_cache_key("https://github.com/user/repo", "abc123456789")
        assert key == "repo-abc12345"


def test_different_conditions_different_keys():
    """Test same repo+commit with different conditions get different keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)
        key1 = cache.get_cache_key("https://github.com/user/repo", "abc123456789", "flat_llm")
        key2 = cache.get_cache_key("https://github.com/user/repo", "abc123456789", "intent_layer")
        assert key1 != key2
        assert "flat_llm" in key1
        assert "intent_layer" in key2


def test_clear():
    """Test clearing cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = IndexCache(tmpdir)

        # Create and save a cache entry
        with tempfile.TemporaryDirectory() as workspace:
            workspace_path = Path(workspace)
            (workspace_path / "CLAUDE.md").write_text("# Root")

            cache.save(
                "https://github.com/user/repo",
                "abc123",
                workspace,
                ["CLAUDE.md"]
            )

        # Verify entry exists
        assert len(cache.manifest.entries) == 1

        # Clear cache
        cache.clear()

        # Verify cache is empty
        assert len(cache.manifest.entries) == 0
        entry = cache.lookup("https://github.com/user/repo", "abc123")
        assert entry is None
