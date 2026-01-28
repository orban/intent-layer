# lib/index_cache.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from datetime import datetime
from urllib.parse import urlparse


@dataclass
class CacheEntry:
    repo: str
    commit: str
    workspace_path: str
    created_at: str
    agents_files: list[str]


@dataclass
class CacheManifest:
    entries: dict[str, CacheEntry]


class IndexCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.cache_dir / "cache-manifest.json"
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> CacheManifest:
        """Load manifest from disk or create empty one."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                data = json.load(f)
                entries = {
                    k: CacheEntry(**v) for k, v in data.get("entries", {}).items()
                }
                return CacheManifest(entries=entries)
        else:
            manifest = CacheManifest(entries={})
            # Save empty manifest
            data = {"entries": {}}
            with open(self.manifest_path, "w") as f:
                json.dump(data, f, indent=2)
            return manifest

    def _save_manifest(self):
        """Save manifest to disk."""
        data = {
            "entries": {
                k: {
                    "repo": v.repo,
                    "commit": v.commit,
                    "workspace_path": v.workspace_path,
                    "created_at": v.created_at,
                    "agents_files": v.agents_files
                }
                for k, v in self.manifest.entries.items()
            }
        }
        with open(self.manifest_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_cache_key(self, repo: str, commit: str) -> str:
        """Generate cache key from repo URL and commit SHA.

        Args:
            repo: Repository URL (e.g., https://github.com/user/repo)
            commit: Full commit SHA

        Returns:
            Cache key in format: <repo-name>-<commit[:8]>
        """
        # Extract repo name from URL
        parsed = urlparse(repo)
        repo_name = parsed.path.strip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        # Use first 8 chars of commit
        commit_short = commit[:8]

        return f"{repo_name}-{commit_short}"

    def lookup(self, repo: str, commit: str) -> CacheEntry | None:
        """Look up cached index by repo and commit.

        Args:
            repo: Repository URL
            commit: Full commit SHA

        Returns:
            CacheEntry if found, None otherwise
        """
        cache_key = self.get_cache_key(repo, commit)
        return self.manifest.entries.get(cache_key)

    def save(self, repo: str, commit: str, workspace: str, agents_files: list[str]):
        """Save generated index to cache.

        Args:
            repo: Repository URL
            commit: Full commit SHA
            workspace: Path to workspace containing generated files
            agents_files: List of relative paths to AGENTS.md/CLAUDE.md files
        """
        # Create cache entry directory
        cache_key = self.get_cache_key(repo, commit)
        cache_entry_dir = self.cache_dir / cache_key
        cache_entry_dir.mkdir(parents=True, exist_ok=True)

        # Copy AGENTS.md files to cache
        workspace_path = Path(workspace)
        for agents_file in agents_files:
            src = workspace_path / agents_file
            dst = cache_entry_dir / agents_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                import shutil
                shutil.copy2(src, dst)

        # Update manifest
        entry = CacheEntry(
            repo=repo,
            commit=commit,
            workspace_path=str(cache_entry_dir),
            created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            agents_files=agents_files
        )
        self.manifest.entries[cache_key] = entry
        self._save_manifest()

    def restore(self, entry: CacheEntry, target_workspace: str):
        """Restore cached AGENTS.md files to target workspace.

        Args:
            entry: CacheEntry to restore from
            target_workspace: Path to workspace to restore files into
        """
        import shutil
        cache_entry_dir = Path(entry.workspace_path)
        target_path = Path(target_workspace)

        for agents_file in entry.agents_files:
            src = cache_entry_dir / agents_file
            dst = target_path / agents_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dst)

    def clear(self):
        """Clear all cached indexes."""
        import shutil
        for entry in self.manifest.entries.values():
            entry_path = Path(entry.workspace_path)
            if entry_path.exists():
                shutil.rmtree(entry_path)

        self.manifest.entries = {}
        self._save_manifest()
