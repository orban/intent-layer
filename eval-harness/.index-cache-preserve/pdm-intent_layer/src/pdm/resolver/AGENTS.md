# Resolver — AGENTS.md

## Purpose

Dual resolver: `RLResolver` (resolvelib) and `UvResolver` (uv lock subprocess). Provider strategies, graph post-processing.

## Entry Points

| Task | Start Here |
|------|------------|
| Fix resolution strategy | `providers.py` — `BaseProvider` + `_PROVIDER_REGISTRY` |
| Fix resolvelib integration | `resolvelib.py` — `RLResolver` |
| Fix uv resolver | `uv.py` — `UvResolver` |
| Fix marker propagation | `graph.py` — `merge_markers` |
| Fix Python constraint handling | `python.py` — `PythonRequirement` |

## Code Map

| File | Purpose |
|---|---|
| `base.py` | Abstract `Resolver`, `Resolution` named tuple |
| `providers.py` | `BaseProvider` + strategy subclasses, `_PROVIDER_REGISTRY` |
| `resolvelib.py` | `RLResolver` — calls resolvelib, builds `Package` list |
| `uv.py` | `UvResolver` — shells out to `uv lock`, parses `uv.lock` |
| `python.py` | `PythonRequirement`/`PythonCandidate` — Python as a synthetic dep |
| `graph.py` | `merge_markers`, `populate_groups` — post-resolution marker propagation |
| `reporters.py` | `LockReporter` (log) and `RichLockReporter` (progress UI) |

## Key Relationships

- `RLResolver.__post_init__` calls `project.get_provider(...)` — provider construction is delegated.
- `BaseProvider` takes a `repository: BaseRepository`. Provider doesn't touch network directly.
- `ReusePinProvider` checks `locked_repository` for cached deps before hitting live repo.
- `UvResolver` uses `formats/uv.py:uv_file_builder` to generate temp pyproject + uv.lock.
- Python interpreter is a first-class synthetic requirement — allows resolvelib to backtrack on Python conflicts.

## Contracts

- `update_strategy` must be in `_PROVIDER_REGISTRY`: `"all"`, `"reuse"`, `"eager"`, `"reuse-installed"`.
- `UvResolver` only supports `all` and `reuse`. Others fallback to `reuse` with warning.
- `BaseProvider.get_preference` always prioritizes Python (`not is_python` is first tuple element).
- `find_matches` returns a callable returning an iterator (resolvelib's lazy contract).
- `merge_markers` handles circular deps with a two-pass approach. Don't assume single-pass resolution.
- `UvResolver` requires a virtual environment. Sets `UV_PROJECT_ENVIRONMENT` in subprocess.

## Pitfalls

### `UvResolver` doesn't support cross-platform resolution

When `target.platform` differs from current machine, uv resolves against the *current* machine. Warns but doesn't error — result may be incorrect.

### `eager` strategy mutates `tracked_names` as side effect

`EagerUpdateProvider.get_dependencies` adds dep keys to `self.tracked_names` cumulatively. Multiple calls expand tracking.

### `BaseProvider.overrides` is a `cached_property`

Override files parsed once and cached. State changes after construction aren't reflected.

### `:empty:` key in resolver mapping

Source distributions whose name wasn't known until after build get a `:empty:` key. `RLResolver._do_resolve` renames them, but code consuming `result.mapping` directly will see `:empty:`.

### Resolution overrides drop extra dependencies (#3428)

Using `[tool.pdm.resolution.overrides]` could silently drop extras from transitive deps.

### UV mode: transitive extras not installed (#3559)

Extra dependencies of transitive deps weren't forwarded to `uv sync` properly.

### Prerelease condition logic (#3645)

`BaseProvider` had incorrect prerelease condition logic — prereleases were allowed/disallowed in wrong contexts.

### `pdm lock --update-reuse` with URL deps (#3463)

URL dependencies generated invalid lock files when using `--update-reuse`.
