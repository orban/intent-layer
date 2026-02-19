# module_utils

Shared utilities shipped to remote targets alongside modules. BSD-2-Clause licensed (more permissive than the rest of ansible-core).

## Isolation boundary (CRITICAL)

`module_utils` cannot import from anything outside itself. Modules can only import from `module_utils`. This is enforced by AnsiballZ packaging: only `module_utils` code is bundled and sent to the target machine.

## Structure

- `basic.py` — `AnsibleModule` base class (~22k tokens). Argument parsing, check mode, atomic file operations, `run_command()`, `exit_json()`/`fail_json()`. Target-side Python minimum is 3.9 (`_PY_MIN`).
- `common/` — shared helpers: argument spec validation (`arg_spec.py`, `parameters.py`), text converters, file operations, YAML loading, process management, sentinel value
- `facts/` — system fact gathering (hardware, network, virtual, system, OS distribution detection). `hardware/linux.py` is the largest (~9.5k tokens).
- `distro/` — vendored `distro` library for OS detection (`_distro.py` ~12k tokens)
- `urls.py` — HTTP client (~14k tokens). `fetch_url()`, `open_url()`, cookie and CA cert handling
- `_internal/` — private internals shared between controller and target: datatag, JSON serialization, deprecation, AnsiballZ extensions
- `csharp/` — C# module utilities for Windows (`Ansible.Basic.cs` ~20k tokens)
- `powershell/` — PowerShell module utilities for Windows
- `six/` — vendored `six` library (deprecated as of v2.21, commit 686c365)
- `parsing/` — boolean conversion, URL splitting
- `compat/` — compatibility shims (selinux)

## Contracts

- `AnsibleModule` arguments are declared via `argument_spec` dict. Validation is automatic.
- Module results must be returned via `module.exit_json(**result)` (success) or `module.fail_json(msg=..., **result)` (failure). Never use `sys.exit()` or `print()`.
- `run_command()` is the safe way to execute external commands. Handles encoding, PATH, and returns (rc, stdout, stderr).
- `human_to_bytes()` converts size strings ("10M", "1G") to integer bytes. Accepts both SI and IEC units.
- `get_bin_path()` locates executables. The `required` parameter was removed in v2.21 (commit 9f1177a); it now always raises on missing binaries.

## Pitfalls

- `basic.py` deprecated imports were removed in v2.21 (commit 2e8a859). Don't import `get_exception`, `BOOLEANS`, `BOOLEANS_TRUE`, `BOOLEANS_FALSE` from `basic`.
- `ansible.module_utils.six` is deprecated (commit 686c365). Use stdlib equivalents.
- `compat.datetime` APIs were removed (commit 367de44).
- `human_to_bytes` had a parsing bug with certain unit formats (commit 13a7393). Test edge cases with mixed-case units.
- Sensitive information remembered by `AnsibleModule` for later use was reverted due to issues (commits 19e9f3d, then revert fd76cc2). Don't cache user-provided secrets on the module object.
- Windows async wrapper code was refactored (commit 101e2eb). PowerShell async modules have different serialization requirements.
- ClearLinux distribution detection was broken by Gentoo-style parsing (commit 869088b). Distribution fact code must handle overlapping `/etc/*-release` formats.
- `fetch_file()` gained `ca_path` and `cookies` parameters (commit 1cd4369). Older code passing positional args may break.
- Module respawn: `PYTHONPATH` must be explicitly set in the `ENV` dict copy, not inherited from the LIB env var (commit 82e4b46).
