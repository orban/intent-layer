# Project — AGENTS.md

## Purpose

Project core class, configuration, pyproject.toml handling, lockfile formats (pdm.lock + pylock.toml).

## Entry Points

| Task | Start Here |
|------|------------|
| Fix config key behavior | `config.py` — `Config._config_map` |
| Fix pyproject.toml parsing | `project_file.py` — `PyProject` |
| Fix lockfile read/write | `lockfile/pdmlock.py` or `lockfile/pylock.py` |
| Fix lockfile format detection | `lockfile/__init__.py` — `load_lockfile()` |
| Fix content hash staleness | `project_file.py` — `content_hash()` |

## Design Rationale

`Project` is the central service locator — holds config, pyproject, lockfile, environment, and cache objects. It doesn't resolve or install; it provides the configured objects that do.

**Two-tier config**: `Config` uses `ChainMap` layering (env vars → file → defaults). Env vars always win.

**Lazy TOML parsing**: `TOMLFile` uses fast `tomllib` for reads, switches to `tomlkit` only on `open_for_write()` to preserve formatting.

**Auto-conversion**: `PyProject._parse()` silently converts flit/poetry formats at read time. Consumers never see the original.

## Code Map

| Looking for... | Go to |
|---|---|
| Main project object | `core.py` — `class Project` |
| Read pyproject.toml | `project_file.py` — `class PyProject` |
| All config keys and defaults | `config.py` — `Config._config_map` |
| Config key lookup with env var fallback | `config.py` — `class EnvMap` |
| Load lockfile (auto-detect format) | `lockfile/__init__.py` — `load_lockfile()` |
| PDM native lockfile | `lockfile/pdmlock.py` — `class PDMLock` |
| PEP 751 lockfile | `lockfile/pylock.py` — `class PyLock` |
| Content hash for staleness | `project_file.py` — `PyProject.content_hash()` |
| All dependencies by group | `core.py` — `Project.get_dependencies()` |

## Contracts

- `TOMLFile.open_for_write()` must precede `write()`. Read mode uses `tomllib`; write re-parses with `tomlkit`.
- `Config._config_map` is a class variable. `add_config()` modifies it globally.
- `Config.__getitem__` applies `ConfigItem.coerce` on every get, not on set.
- `load_lockfile()` detects format from content, not filename. `config["lock.format"]` only applies to new lockfiles.
- `Lockfile.format_lockfile()` replaces all content, not a merge.
- `FLAG_INHERIT_METADATA` is required for pylock format — `PyLock.format_lockfile()` raises without it.
- `content_hash()` covers: source, dependencies, dev-dependencies, optional-dependencies, requires-python, resolution. Build config is NOT included.

## Pitfalls

### `dev_dependencies` merges two sources silently

`PyProject.dev_dependencies` reads from both `[dependency-groups]` (PEP 735) and `[tool.pdm.dev-dependencies]` (legacy). Same normalized name in both sections? Cross-section merges silently stack via `setdefault().extend()`. Only `[dependency-groups]` internal duplicates raise `ProjectError`.

### `_convert_pyproject()` runs on `open_for_write()`

Opening a flit/poetry project for write mutates the in-memory tomlkit doc. `write()` produces a PDM-format file. No opt-out.

### `Lockfile.compatibility()` returns `SAME` when file doesn't exist

A missing lockfile is treated as "up to date." Callers must check existence separately.

### Config env var shadowing is a warning, not an error

Setting a config key that has an active env var writes the value but the env var still wins on next read.

### Project config has no defaults layer

Global `Config` ChainMap has three layers; project config only has the file layer. Missing keys fall through to `NoConfigError` even if `_config_map` has a default.

### Hash clearing on lockfile env_spec append (#3611)

Appending to a lockfile with a new `env_spec` was clearing hashes for existing entries.

### Package metadata missing from lockfile after 2.25 (#3547)

Reading locked candidates after version 2.25 format changes could lose metadata. Fixed by searching lock file metadata first when reusing.

### Adding dependency duplicates lockfile entries (#3546)

`do_lock` with `--update-reuse` could duplicate entries. Fixed by deduplicating on candidate key.

### `pdm.toml` not found during pre_build hook (#3621)

`pdm.toml` created on-the-fly in a `pre_build` hook wasn't picked up by `pdm build` because config was loaded before hooks ran.
