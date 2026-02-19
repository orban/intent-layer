# CLAUDE.md

## Purpose

PDM — a Python package and dependency manager supporting PEP standards. Dual resolver (resolvelib + uv), dual lockfile format (pdm.lock + pylock.toml), plugin system via entry points.

## Build, Test, Run

```bash
# Install dev dependencies
pdm install -d

# Run tests (uses pytest, pdm.pytest plugin provides fixtures)
pdm run pytest tests/ -x
pdm run pytest tests/cli/test_add.py -k "test_add_package"  # single test

# Tests requiring network: marked with @pytest.mark.network
# Tests requiring uv: marked with @pytest.mark.uv (skipped if uv not installed)

# Build
pdm build

# Lint (pre-commit)
pre-commit run --all-files
```

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new CLI command | `src/pdm/cli/commands/` — create module with `Command` class |
| Fix dependency resolution | `src/pdm/resolver/` — `providers.py` for strategy, `resolvelib.py`/`uv.py` for backends |
| Fix install/sync issues | `src/pdm/installers/synchronizers.py` — diff logic in `compare_with_working_set` |
| Fix lockfile read/write | `src/pdm/project/lockfile/` — `pdmlock.py` or `pylock.py` |
| Fix requirement parsing | `src/pdm/models/requirements.py` — `parse_line()` / `parse_requirement()` |
| Fix marker/specifier logic | `src/pdm/models/markers.py` and `specifiers.py` |
| Fix project config | `src/pdm/project/config.py` — `Config._config_map` has all keys |
| Fix format import/export | `src/pdm/formats/` — protocol: `check_fingerprint`, `convert`, `export` |
| Write a plugin | `src/pdm/core.py` — entry point group `"pdm"`, receives `Core` instance |
| Understand test fixtures | `src/pdm/pytest.py` — `pdm`, `project`, `repository`, `working_set` fixtures |

## Code Map

```
CLI Layer (cli/)
  ├── commands/*.py      argparse subcommands
  ├── actions.py         shared operations (do_lock, do_sync)
  ├── hooks.py           signal-based lifecycle hooks
  └── filters.py         group selection logic

Domain Layer
  ├── models/            requirements, candidates, markers, specifiers, caches
  ├── project/           Project class, config, pyproject, lockfile
  ├── resolver/          resolvelib + uv backends, providers, graph
  └── formats/           import from poetry/flit/pipfile, export to requirements.txt/pylock

Execution Layer
  ├── installers/        synchronizers (diff + apply), wheel install, uninstall
  ├── environments/      venv, PEP 582, bare env
  └── builders/          sdist, wheel, editable builds
```

Data flows top-to-bottom: CLI calls `actions.py`, which uses `resolver` to produce `Resolution`, then `installers` to apply it. `models/` and `project/` are shared across all layers.

### Plugin System

Plugins load from `"pdm"` and `"pdm.plugin"` entry point groups. A plugin is a callable receiving `Core`:

```python
def my_plugin(core):
    core.register_command(MyCommand)        # add CLI command
    Config.add_config("key", ConfigItem())  # add config key (modifies class-level dict)
    Core.project_class = MyProject          # swap project class
```

Failures are logged but don't abort startup.

### Dual Resolver

- `RLResolver` — wraps `resolvelib`. Four strategies: `all`, `reuse`, `eager`, `reuse-installed`.
- `UvResolver` — shells out to `uv lock`. Only supports `all` and `reuse`; warns on others.

### Dual Lockfile

- `pdm.lock` — PDM native format. Detected by `metadata.lock_version` key.
- `pylock.toml` — PEP 751 format. Detected by `lock-version` key. Requires `FLAG_INHERIT_METADATA`.
- Format detection is content-based, not filename-based.

## Contracts

- **Command registration**: auto-discovery looks for `module.Command` exactly. Other names are silently skipped.
- **`Requirement` identity**: `__eq__` and `__hash__` use `(key, extras, marker)` — NOT version specifier. Two reqs for the same package at different versions are "equal."
- **`Requirement.key` is always lowercase-normalized**: never call `.lower()` on it again.
- **`TOMLFile` write gate**: `open_for_write()` must be called before `write()`. Read uses fast `tomllib`; write re-parses with `tomlkit` to preserve formatting.
- **`Config._config_map` is a class variable**: `add_config()` affects all instances globally.
- **`content_hash()` scope**: covers dependencies, requires-python, resolution config. Does NOT include build backend config.
- **Group name `"default"` is reserved**: `GroupSelection` always sorts it first. Can't be used as a dependency group name.

## Pitfalls

### Lockfile hash clearing on env_spec append (#3611)

Appending to a lockfile with a new `env_spec` was clearing hashes for existing entries. The fix ensures hashes are preserved when merging lock targets.

### Circular file dependencies cause infinite recursion (#3539)

`FileRequirement.__post_init__` calls `Setup.from_directory()` which walks the filesystem. A project depending on itself via path creates infinite recursion. Guarded by `_checked_paths` module-level set — but it's not thread-safe and not cleared between test runs.

### Adding dependency duplicates lockfile entries (#3546)

`do_lock` with `--update-reuse` could duplicate entries when appending. Fixed by deduplicating on the candidate key.

### Resolution overrides drop extra dependencies (#3428)

Using `[tool.pdm.resolution.overrides]` could silently drop extras from transitive dependencies. The override was applied too broadly.

### `pdm add`/`update` remove dependency groups incorrectly (#3419)

Group manipulation in add/update was using incorrect group filtering, removing groups that shouldn't be touched.

### UV mode: transitive extras not installed (#3559)

When `USE_UV=true`, extra dependencies of transitive dependencies weren't properly forwarded to `uv sync`.

### `packaging` 26 compatibility (#3730)

`packaging` 26 changed APIs. PDM's `specifiers.py` and related code needed updates to handle the new version.

### pylock.toml + git dependency lock failure (#3695)

Git dependencies caused `format_lockfile()` to fail because the pylock converter didn't handle VCS URLs.

### `PdmUsageError` suppresses tracebacks

Any subclass of `PdmUsageError` prints without traceback at normal verbosity. Use `-v` to see the stack. Other `PdmException` subclasses show "add -v" hint.

### `Project` stored as `weakref.proxy` in environments

`isinstance(env.project, Project)` returns `False`. Don't pass `env.project` to functions that check `isinstance`.

## Intent Layer

### Downlinks

| Area | Node | Description |
|------|------|-------------|
| CLI | `src/pdm/cli/AGENTS.md` | Command registration, actions, hooks, group selection |
| Models | `src/pdm/models/AGENTS.md` | Requirements, candidates, markers, specifiers, caches, repositories |
| Project | `src/pdm/project/AGENTS.md` | Project core, config, pyproject, lockfile formats |
| Resolver | `src/pdm/resolver/AGENTS.md` | Dual resolver (resolvelib + uv), providers, graph |
| Installers | `src/pdm/installers/AGENTS.md` | Synchronizers, wheel install, uninstall, caching |
| Formats | `src/pdm/formats/AGENTS.md` | Import/export: poetry, flit, pipfile, requirements.txt, pylock |
