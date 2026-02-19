# Formats — AGENTS.md

## Purpose

Import from poetry/flit/pipfile, export to requirements.txt/pylock.toml.

## Entry Points

| Task | Start Here |
|------|------------|
| Fix requirements.txt export | `requirements.py` — `export()` |
| Fix poetry import | `poetry.py` — `PoetryMetaConverter` |
| Fix flit import | `flit.py` — `FlitMetaConverter` |
| Fix pylock.toml output | `pylock.py` — `PyLockConverter` |
| Add new format | `__init__.py` — add to `FORMATS` dict |

## Design Rationale

**Protocol-based dispatch**: `FORMATS` dict maps names to modules conforming to an informal protocol: `check_fingerprint`, `convert`, `export`. Import-only formats raise `NotImplementedError` in `export`.

**`MetaConverter` metaclass pattern**: Subclasses decorate methods with `@convert_from(field, name)`. The metaclass collects these into `._converters`. `convert()` iterates them, collecting errors rather than aborting, then raises `MetaConvertError` with partial results.

## Code Map

| Looking for... | Go to |
|---|---|
| Registered import/export formats | `__init__.py` — `FORMATS` dict |
| Base metaclass converter | `base.py` — `class MetaConverter` |
| `@convert_from` decorator | `base.py` — `convert_from()` |
| Parse requirements.txt | `requirements.py` — `RequirementParser` |
| Export to requirements.txt | `requirements.py` — `export()` |
| Import from Poetry | `poetry.py` — `PoetryMetaConverter` |
| Import from flit | `flit.py` — `FlitMetaConverter` |
| Write pylock.toml content | `pylock.py` — `PyLockConverter` |

## Key Relationships

- `FORMATS` registers: `pipfile`, `poetry`, `flit`, `setup_py`, `requirements`. **`pylock` and `uv` are NOT in `FORMATS`** — used internally only.
- `PyProject._convert_pyproject()` imports `flit` and `poetry` directly for auto-conversion at parse time.
- `PyLock.format_lockfile()` instantiates `PyLockConverter` — only hard dependency from lockfile layer into formats.
- `@convert_from(field=None)` means the method receives the entire source dict and is responsible for `.pop()`ing what it consumes.

## Contracts

- Every format module must implement `check_fingerprint`, `convert`, `export`. No enforcement at import time.
- `convert()` returns `(metadata, settings)` tuple. `metadata` → `[project]`, `settings` → `[tool.pdm]`.
- `MetaConverter` on error raises `MetaConvertError` with `.data` and `.settings` holding partial results.
- `@convert_from` methods that raise `Unset` produce no output key.
- `PyLockConverter.convert()` requires `FLAG_INHERIT_METADATA`. Raises `ProjectError` without it.
- `PyLockConverter._populate_hashes()` makes network calls. Runs inside a spinner.

## Pitfalls

### `check_fingerprint` called with `project=None`

`PyProject._convert_pyproject()` passes `None` as project. Implementations that access `project.something` will raise `AttributeError`.

### Poetry `^` operator is fully expanded

`_convert_specifier("^1.2.3")` → `>=1.2.3,<2.0.0`. No way to recover original constraint. Exporting back to poetry gives expanded form.

### `PoetryMetaConverter.requires_python()` has side effects

It pops `"python"` from `source["dependencies"]` dict. The `dependencies` converter runs after and sees `python` already removed. Converter ordering matters.

### `FORMATS` doesn't include `pylock` or `uv`

Code iterating `FORMATS` for "all supported formats" misses these. The pylock format is write-only. The uv format is invoked directly by import, not registered.

### `RequirementParser` silently drops per-requirement options

Lines like `requests --global-option="..."` — anything after ` -` is stripped. Parser does `line.split(" -", 1)[0]`.

### pylock.toml + git dependency lock failure (#3695)

Git dependencies caused `format_lockfile()` to fail because the pylock converter didn't handle VCS URLs.

### Export from pylock produces empty requirements.txt (#3573)

`pdm export -f pylock` then re-export to requirements.txt produced empty output due to missing URL population.

### Editable local packages cause empty URLs in pylock (#3566)

Editable local packages weren't getting proper URLs when pylock format was used.
