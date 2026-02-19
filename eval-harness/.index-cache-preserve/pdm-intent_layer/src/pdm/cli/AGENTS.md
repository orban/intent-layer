# CLI — AGENTS.md

## Purpose

Commands, argument parsing, shared actions, hook lifecycle, and group selection.

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new CLI command | `commands/` — create module with `Command` class |
| Fix locking behavior | `actions.py` — `do_lock` |
| Fix install/sync flow | `actions.py` — `do_sync` |
| Fix group selection | `filters.py` — `GroupSelection` |
| Fix hook lifecycle | `hooks.py` — `HookManager` |
| Fix CLI option behavior | `options.py` — shared option definitions |

## Code Map

| Looking for... | Go to |
|---|---|
| Shared CLI option definitions (`-G`, `--lockfile`, etc.) | `options.py` |
| Dependency group resolution (`:all`, `--dev`, `--prod`) | `filters.py` — `GroupSelection` |
| Pre/post hook lifecycle | `hooks.py` — `HookManager.try_emit` |
| Locking algorithm entry point | `actions.py` — `do_lock` |
| Install/sync entry point | `actions.py` — `do_sync` |
| Lockfile staleness check | `actions.py` — `check_lockfile` |
| Dependency graph for `pdm list` | `utils.py` — `build_dependency_graph` |
| How commands are auto-registered | `core.py` — `pkgutil.iter_modules` + `register_command` |
| Venv sub-commands | `commands/venv/__init__.py` |
| Script runner / composite tasks | `commands/run.py` — `TaskRunner` |
| Save strategy (compatible/wildcard/exact) | `utils.py` — `save_version_specifiers` |

## Key Relationships

```
commands/*.py  →  actions.py  →  models/, project/, installers/
                  filters.py
                  hooks.py
                  options.py
```

Commands are consumers of `actions.py`, never the reverse. `actions.py` calls into `resolver`, `installers`, and `project` layers.

**Command registration**: `Core.init_parser()` auto-discovers modules in `pdm.cli.commands` via `pkgutil.iter_modules`. Looks for `module.Command` — other names silently skipped. The command instance is stored via `parser.set_defaults(command=cmd)`.

**Options callback flow**: Some options (`--frozen-lockfile`, `--no-isolation`) queue callbacks in `namespace.callbacks`. `Core.main()` runs these AFTER project creation. Options that mutate the project (like `enable_write_lockfile`) won't take effect if `do_lock` is called before callbacks run.

## Contracts

- `Command.arguments` is a tuple of `Option`/`ArgumentGroup` instances. Order matters for help output.
- `HookManager` skip semantics: `:all` skips everything, `:pre`/`:post` skip by prefix, individual names are exact matches. OR-combined.
- `GroupSelection.all()` returns `None` (meaning "all groups") vs `list(selection)` which returns concrete groups. Passing `None` to `do_lock(groups=...)` triggers different behavior than passing an explicit list.
- `check_lockfile` returns `"all"` (missing), `"reuse"` (incompatible), or `None` (up to date). Not a boolean.
- `do_add`/`do_remove` on command classes are `@staticmethod` — stable public API despite being on `Command` classes.

## Pitfalls

### `GroupSelection.all()` vs `list(selection)` are semantically different

`all()` returns `None` when unset (means "use all project groups"). `list(selection)` always returns a concrete list. Several commands pass `selection.all()` deliberately for the fallback behavior.

### `save_version_specifiers` mutates `Requirement` objects in place

Modifies `r.specifier` directly. If the same requirement objects are used elsewhere, both callers see the mutated value.

### `PdmFormatter` is skipped on Python 3.14+

`utils.py` switches to `RawDescriptionHelpFormatter` on 3.14+. Don't add logic to `PdmFormatter` expecting it to run everywhere.

### `GroupSelection.validate()` raises on extra groups, not missing ones

It compares requested groups against lockfile groups. A group in `pyproject.toml` but not in the lockfile is silently dropped when `exclude_non_existing=True`.

### `pdm add`/`update` removed dependency groups incorrectly (#3419, #3454)

Group filtering in add/update was removing groups that shouldn't be touched. The override URL and some groups were being dropped from `pdm.lock` upon adding a new dependency.

### `ExtendMapAction` builds a dict, not a list

`--config-setting key=value` produces `{"key": "value"}`, not a list. Repeated keys become `{"key": ["v1", "v2"]}`.
