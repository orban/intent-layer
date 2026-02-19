# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PDM is a Python package and dependency manager supporting PEP 517/621. It provides dependency resolution (via resolvelib or uv), virtual environment management, a plugin system, and a build frontend. Entry point: `pdm.core:main`.

## Development commands

```bash
# Install all dev dependencies
pdm install

# Run full test suite
pdm run test

# Run tests in parallel (much faster)
pdm run test -n auto

# Skip slow integration tests
pdm run test -n auto -m "not integration"

# Run a single test file
pdm run test tests/cli/test_add.py

# Run a single test by name
pdm run test -k "test_add_package"

# Run tests with coverage
pdm run coverage

# Lint (ruff format + ruff lint + codespell + mypy)
pdm run lint

# Serve docs locally
pdm run doc
```

Linting uses `prek` (pre-commit runner). Install it separately, then `prek install` to set up hooks.

### News fragments

Every PR needs a news fragment in `news/` named `<issue_num>.<type>.md` where type is one of: `feature`, `bugfix`, `refactor`, `doc`, `dep`, `removal`, `misc`. Content is a single imperative-mood sentence.

## Architecture

### Core → Project → Environment pipeline

The central flow is: `Core` creates a `Project`, which manages a `BaseEnvironment`, which the resolver and installer operate against.

- **`Core`** (`src/pdm/core.py`): Top-level DI container. Holds `project_class`, `repository_class`, `install_manager_class` as swappable class attributes. Auto-discovers CLI commands via `pkgutil.iter_modules` on `pdm.cli.commands`. Loads plugins from `pdm` and `pdm.plugin` entry point groups.

- **`Project`** (`src/pdm/project/core.py`): Represents a PDM project. Owns `PyProject` (toml parsing), lockfile, config, environment, and Python info. The `root` path is discovered by `find_project_root()` walking up the directory tree.

- **Environments** (`src/pdm/environments/`): `BaseEnvironment` → `PythonEnvironment` (venv-based) and `PythonLocalEnvironment` (PEP 582). `BareEnvironment` is for operations that don't need a real Python.

### Command system

All commands live in `src/pdm/cli/commands/`, one file per command (or directory for sub-commands like `venv/`, `fix/`, `publish/`). Each exports a `Command` class inheriting `BaseCommand`. Registration is automatic — just create the file.

`BaseCommand.arguments` controls which standard options (verbose, project, global) are attached. Override `add_arguments()` for custom args. Override `handle(project, options)` for logic.

The `Option` class (`src/pdm/cli/options.py`) wraps argparse args as reusable objects. The `CallbackAction` pattern lets options register deferred callbacks that run after project creation.

### Resolver

Two resolver backends behind the `Resolver` ABC (`src/pdm/resolver/base.py`):
- `RLResolver` — resolvelib-based, the default
- `UvResolver` — delegates to uv (experimental, set `use_uv = true` in config)

Both produce a `Resolution` containing `Package` entries with pinned `Candidate` objects.

### Installer / Synchronizer

- `InstallManager` (`src/pdm/installers/manager.py`): Handles individual package install/uninstall
- `Synchronizer` / `UvSynchronizer` (`src/pdm/installers/synchronizers.py`, `uv.py`): Orchestrates syncing the full environment against a lockfile
- `install_wheel` in `installers/installers.py`: Low-level wheel installation

### Plugin system

Plugins are callables loaded from entry points (`pdm` or `pdm.plugin` groups). They receive the `Core` instance and can:
- Register new commands via `core.register_command()`
- Add config items via `core.add_config()`
- Connect to signals for lifecycle hooks
- Replace `core.project_class`, `core.repository_class`, or `core.install_manager_class`

Project-local plugins go in `.pdm-plugins/` directory.

### Signal system

`src/pdm/signals.py` uses `blinker.NamedSignal`. Key signals: `pre_lock`, `post_lock`, `pre_install`, `post_install`, `pre_build`, `post_build`, `pre_publish`, `post_publish`, `pre_run`, `post_run`, `pre_invoke`. The `HookManager` (`src/pdm/cli/hooks.py`) wraps signal emission with skip logic (`:all`, `:pre`, `:post`, or individual names).

### Lockfile formats

Two lockfile implementations behind `Lockfile` ABC (`src/pdm/project/lockfile/base.py`):
- `PDMLock` — the default `pdm.lock` format
- `PyLock` — PEP pylock.toml format

### Format converters

`src/pdm/formats/` contains importers/exporters for pipfile, poetry, flit, setup.py, requirements.txt, uv, and pylock. Each module implements `check_fingerprint()`, `convert()`, and `export()`.

### Group selection

`GroupSelection` (`src/pdm/cli/filters.py`) handles dependency group filtering (default, dev, optional groups, exclusions). Many commands accept `--group`, `--dev`, `--no-default` flags that feed into this.

## Test infrastructure

Tests use `pdm.pytest` (`src/pdm/pytest.py`), a public fixture module also usable by plugin developers. Key fixtures:
- `pdm` callable fixture: invokes CLI commands programmatically and captures output
- `project`: a pre-configured test `Project` with mocked PyPI indexes
- `pypi_indexes` / `index`: mock package index serving from `tests/fixtures/`
- `build_env_wheels`: pre-built wheels for build backends

Test data lives in `tests/fixtures/` — artifacts (wheels/tarballs), mock index HTML, sample projects, and lockfiles.

Markers: `@pytest.mark.network` (needs internet), `@pytest.mark.integration` (run with all Python versions), `@pytest.mark.path` (system path comparison), `@pytest.mark.uv` (needs uv installed).

## Key config

- **ruff**: line-length 120, target py38, isort + bugbear + comprehensions enabled. `tests/fixtures` excluded.
- **mypy**: strict (disallow_untyped_defs/decorators), namespace packages, `src/` as mypy_path. Excludes `pep582/`, `models/in_process/`, `misc/`.
- Python support: 3.9+
