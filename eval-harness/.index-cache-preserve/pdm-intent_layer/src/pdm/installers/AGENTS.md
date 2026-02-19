# Installers — AGENTS.md

## Purpose

Synchronizers (diff + apply), wheel installation, uninstallation, install caching.

## Entry Points

| Task | Start Here |
|------|------------|
| Fix install diff logic | `base.py` — `BaseSynchronizer.compare_with_working_set` |
| Fix parallel install | `synchronizers.py` — `Synchronizer` |
| Fix uv sync | `uv.py` — `UvSynchronizer` |
| Fix wheel install | `installers.py` — `install_wheel` |
| Fix uninstall | `uninstallers.py` — `StashedRemovePaths` |
| Fix install caching | `manager.py` — `InstallManager` |

## Design Rationale

Two parallel hierarchies:
1. **Synchronizer**: computes diff between resolved candidates and working set, dispatches install/update/remove. `Synchronizer` adds Rich UI + parallel execution. `UvSynchronizer` delegates to `uv sync`.
2. **InstallManager**: handles individual wheel install/uninstall. Used by `Synchronizer` but NOT by `UvSynchronizer`.

Uninstallation is transactional via `StashedRemovePaths` — files moved to temp dir before deletion, rollback on failure.

## Code Map

| File | Purpose |
|---|---|
| `base.py` | `BaseSynchronizer` — diff logic (`compare_with_working_set`) |
| `synchronizers.py` | `Synchronizer` — Rich UI, parallel install via `ThreadPoolExecutor` |
| `uv.py` | `UvSynchronizer` — delegates to `uv sync` subprocess |
| `manager.py` | `InstallManager` — single-dist install/uninstall/overwrite |
| `installers.py` | `install_wheel`, `InstallDestination` — low-level wheel install |
| `uninstallers.py` | `StashedRemovePaths` — transactional file removal |
| `core.py` | `install_requirements` — convenience: resolve + sync in one call |

## Contracts

- `BaseSynchronizer.synchronize()` must be called after construction — construction doesn't touch filesystem.
- `compare_with_working_set` returns `(to_add, to_update, to_remove)` as sorted lists of string keys.
- `InstallManager.overwrite` installs new first, then removes only non-overlapping old files. Not remove-then-install.
- `StashedRemovePaths`: must call `remove()` then `commit()` in sequence. `rollback()` without prior `remove()` is a no-op.
- `UvSynchronizer` requires a venv. Raises `ProjectError` without one. Also rejects PEP 582 mode.
- `install_wheel` writes `INSTALLER: pdm` metadata and optionally `direct_url.json`.
- Sequential packages: `pip`, `setuptools`, `wheel` — always installed sequentially, never in parallel.
- Editable packages are always installed sequentially.

## Pitfalls

### `.pdmtmp` pth files persist on crash

Parallel installation uses `.pdmtmp` suffix on `.pth` files. If process is killed before `_fix_pth_files` runs, packages won't be importable until suffix is stripped. Running `pdm install` again fixes it.

### `editables` package bypasses install cache

`InstallManager.NO_CACHE_PACKAGES = ("editables",)`. The `editables` helper writes `.pth` files referencing paths — caching it causes incorrect behavior.

### `overwrite` leaves orphan files

`StashedRemovePaths.difference_update` excludes directories containing new install files from removal. Old files in those directories that the new install doesn't cover are silently left behind.

### `UvSynchronizer` with `dry_run=True` provides no output

uv has no dry-run mode. The synchronizer prints a warning and exits — callers get no information.

### `compare_with_working_set` uses `locked_repository.all_candidates`

A package removed from resolution but still in old lockfile won't be cleaned unless `--clean` or `--only-keep` is used.

### Install self for BaseSynchronizer (#3491)

Self-installation logic had a bug where the project itself wasn't being installed in certain synchronizer configurations.

### Non-existent library paths skipped (#3561)

The synchronizer was failing on non-existent library paths. Fixed by adding existence checks before attempting to process them.

### Reinstalling local wheel should check signature (#3514)

Local wheel reinstalls weren't checking the package signature, potentially leaving stale installs.
