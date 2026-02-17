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
        """Load manifest from disk, repair orphan directories, or create empty."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                data = json.load(f)
                entries = {
                    k: CacheEntry(**v) for k, v in data.get("entries", {}).items()
                }
                manifest = CacheManifest(entries=entries)
        else:
            manifest = CacheManifest(entries={})

        # Repair: scan for directories not in the manifest (orphaned by killed runs)
        repaired = 0
        for child in sorted(self.cache_dir.iterdir()):
            if not child.is_dir() or child.name in manifest.entries:
                continue
            # Find .md files to reconstruct the entry
            md_files = sorted(
                str(p.relative_to(child))
                for p in child.rglob("*.md")
                if p.is_file()
            )
            if not md_files:
                continue
            # Infer repo and commit from directory name:
            #   Per-commit: <repo>-<commit8>-<condition>  (3 parts)
            #   Repo-level: <repo>-<condition>            (2 parts)
            parts = child.name.rsplit("-", 2)
            if len(parts) == 3:
                repo_name, commit_short, condition = parts
            elif len(parts) == 2:
                repo_name, condition = parts
                commit_short = "latest"  # repo-level entry
            else:
                continue
            manifest.entries[child.name] = CacheEntry(
                repo=f"https://github.com/unknown/{repo_name}",
                commit=commit_short,
                workspace_path=str(child),
                created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                agents_files=md_files,
            )
            repaired += 1

        if repaired:
            import logging
            logging.getLogger(__name__).info("Repaired %d orphan cache entries", repaired)

        # Persist (creates file if new, updates if repaired)
        self.manifest = manifest
        self._save_manifest()
        return manifest

    def _save_manifest(self):
        """Save manifest to disk atomically (write tmp + rename)."""
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
        tmp_path = self.manifest_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        tmp_path.rename(self.manifest_path)

    def get_cache_key(self, repo: str, commit: str, condition: str = "") -> str:
        """Generate cache key from repo URL, commit SHA, and condition.

        Args:
            repo: Repository URL (e.g., https://github.com/user/repo)
            commit: Full commit SHA
            condition: Condition name (e.g., "flat_llm", "intent_layer")

        Returns:
            Cache key in format: <repo-name>-<commit[:8]>-<condition>
            If condition is empty, format is: <repo-name>-<commit[:8]>
        """
        repo_name = self._extract_repo_name(repo)
        commit_short = commit[:8]

        if condition:
            return f"{repo_name}-{commit_short}-{condition}"
        return f"{repo_name}-{commit_short}"

    def get_repo_cache_key(self, repo: str, condition: str) -> str:
        """Generate a repo-level cache key (no commit).

        Context files (AGENTS.md, CLAUDE.md) describe repo structure and
        conventions, which don't change between nearby commits. This key
        allows a single generation to serve all tasks in the same repo.

        Returns:
            Cache key in format: <repo-name>-<condition>
        """
        repo_name = self._extract_repo_name(repo)
        return f"{repo_name}-{condition}"

    @staticmethod
    def _extract_repo_name(repo: str) -> str:
        parsed = urlparse(repo)
        repo_name = parsed.path.strip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        return repo_name

    def lookup(self, repo: str, commit: str, condition: str = "") -> CacheEntry | None:
        """Look up cached index by repo, commit, and condition.

        Args:
            repo: Repository URL
            commit: Full commit SHA
            condition: Condition name (e.g., "flat_llm", "intent_layer")

        Returns:
            CacheEntry if found, None otherwise
        """
        cache_key = self.get_cache_key(repo, commit, condition)
        return self.manifest.entries.get(cache_key)

    def lookup_repo(self, repo: str, condition: str) -> CacheEntry | None:
        """Look up cached index by repo and condition (ignoring commit).

        Context files describe repo structure, which is stable across nearby
        commits. This allows one generation to serve all tasks in a repo.

        Returns:
            CacheEntry if found, None otherwise
        """
        cache_key = self.get_repo_cache_key(repo, condition)
        return self.manifest.entries.get(cache_key)

    def save(self, repo: str, commit: str, workspace: str, agents_files: list[str], condition: str = "", repo_level: bool = False):
        """Save generated index to cache.

        Args:
            repo: Repository URL
            commit: Full commit SHA (or any string for repo-level)
            workspace: Path to workspace containing generated files
            agents_files: List of relative paths to AGENTS.md/CLAUDE.md files
            condition: Condition name (e.g., "flat_llm", "intent_layer")
            repo_level: If True, cache by repo+condition only (no commit)
        """
        # Create cache entry directory
        if repo_level:
            cache_key = self.get_repo_cache_key(repo, condition)
        else:
            cache_key = self.get_cache_key(repo, commit, condition)
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
