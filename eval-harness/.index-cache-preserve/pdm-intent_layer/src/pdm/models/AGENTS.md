# Models — AGENTS.md

## Purpose

Core domain types: requirements, candidates, markers, specifiers, caches, repositories, working set.

## Entry Points

| Task | Start Here |
|------|------------|
| Fix requirement parsing | `requirements.py` — `parse_line()` / `parse_requirement()` |
| Fix marker evaluation | `markers.py` — `Marker.matches()` / `split_pyspec()` |
| Fix version specifiers | `specifiers.py` — `PySpecSet` |
| Fix package discovery | `repositories/pypi.py` — `PyPIRepository` |
| Fix lockfile candidate reading | `repositories/lock.py` — `LockedRepository` |
| Fix HTTP/auth issues | `session.py` / `auth.py` |

## Design Rationale

Three-tier split: `Requirement` (spec) → `Candidate` (concrete match) → `PreparedCandidate` (ready to install). This governs most interactions between resolver, installers, and lockfile.

Marker/specifier logic wraps `dep_logic` and `packaging` with PDM-specific merge operators and Python-version splitting.

## Code Map

| Looking for... | Go to |
|---|---|
| Parse requirement string `"requests>=2.0"` | `requirements.py` → `parse_line()` / `parse_requirement()` |
| Parse `-e ./local/path` | `requirements.py` → `parse_line()` (strips `-e`, sets `editable=True`) |
| VCS URL normalization | `requirements.py` → `VcsRequirement._parse_url()` |
| Combine Python version constraints | `specifiers.py` → `PySpecSet.__and__` / `__or__` |
| Convert specifier to marker string | `specifiers.py` → `PySpecSet.as_marker_string()` |
| Split `python_version` from marker | `markers.py` → `Marker.split_pyspec()` |
| Candidate → lockfile dict | `candidates.py` → `Candidate.as_lockfile_entry()` |
| Build/download a candidate | `candidates.py` → `PreparedCandidate.build()` / `_obtain()` |
| HTTP client with caching | `session.py` → `PDMPyPIClient` |
| Credential resolution (netrc, keyring) | `auth.py` → `PdmBasicAuth` |
| Installed packages (sys.path) | `working_set.py` → `WorkingSet` |
| Read lockfile into candidates | `repositories/lock.py` → `LockedRepository` |
| Fetch candidates from PyPI | `repositories/pypi.py` → `PyPIRepository` |

## Type Hierarchy

```
Requirement (base, @dataclass eq=False)
  ├── NamedRequirement       versioned deps
  ├── FileRequirement        local paths + URLs
  └── VcsRequirement         git/hg/svn/bzr

BaseRepository
  ├── PyPIRepository         live index lookups
  └── LockedRepository       reads pdm.lock or pylock.toml
```

## Contracts

- **Requirement identity**: `__eq__`/`__hash__` based on `(key, extras, marker)` — NOT version. Two reqs for same package at different versions hash the same. Intentional for resolver identity.
- **`Requirement.key` is always lowercase-normalized**.
- **`FileRequirement` has filesystem side effects**: `__post_init__` calls `Setup.from_directory()`. Guarded by `_checked_paths` set (not thread-safe, not cleared between tests).
- **`PreparedCandidate.metadata` triggers build on first access**: accessing `.metadata` may download, unpack, and PEP 517 build. Must be inside an active environment context.
- **`CandidateInfoCache` key requires both name and version**: missing either always causes a cache miss (intentional).
- **`WorkingSet` normalizes names on insertion**: keys are `normalize_name(dist.metadata["Name"])`. Lookups must use normalized form.
- **`LockedRepository` format detection**: checks for `"lock-version"` key (pylock) vs `"metadata.lock_version"` (pdm native). Absence of `"lock-version"` signals pdm format.
- **`PySpecSet("<empty>")` is a sentinel**: round-trips through `str()` + constructor, but NOT through `packaging.SpecifierSet`.

## Pitfalls

### `FileRequirement` constructor walks the filesystem

Constructing a `FileRequirement` with a local path triggers `Setup.from_directory()` during `__post_init__`. The `_checked_paths` guard is a module-level set — not thread-safe and not cleared between test runs without module reload.

### Requirement equality ignores specifier version

`parse_requirement("requests>=1.0")` and `parse_requirement("requests>=2.0")` are equal and produce the same hash. Storing in a `dict` keyed by the requirement object silently loses version constraints.

### `PySpecSet.as_marker_string()` raises on empty specifiers

Callers must check `is_empty()` first. The resolver guards this, but code in formats or CLI may not.

### `BaseRepository.get_dependencies` swallows intermediate errors

`dependency_generators()` defines a priority chain. All `CandidateInfoNotFound` exceptions except the final one are silently retried with the next getter. Debugging why a build was triggered is non-obvious.

### `PDMPackageFinder` with `minimal_version=True` uses `ReverseVersion`

Subclasses `packaging.version.Version` to flip comparison. Mixing `ReverseVersion` with normal `Version` comparisons gives inverted results silently.

### `Marker.split_pyspec()` LRU cache is per-class, not per-instance

1024-slot cache fills with stale entries under long-running processes.

### Huge debug logging with keyring + AWS index (#3642)

`PdmBasicAuth` was generating excessive debug logs when keyring was active with private AWS indexes.

### `resolution.excludes` not applied to lock candidates (#3727)

Lock file candidate evaluation wasn't respecting `resolution.excludes`, allowing excluded packages through during reuse.
