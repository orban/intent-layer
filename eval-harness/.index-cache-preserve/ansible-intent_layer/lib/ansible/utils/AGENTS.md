# Utils

Controller-side utility functions. Unlike `module_utils`, these are NOT shipped to targets.

## Key files

- `display.py` — `Display` singleton (~10.8k tokens). All user-facing output goes through this: `display()`, `v()`-`vvvvvv()` (verbosity levels), `warning()`, `error()`, `deprecated()`. Uses ctypes `wcwidth`/`wcswidth` for terminal width. Thread-safe via locking. Supports worker-process queue forwarding.
- `collection_loader/_collection_finder.py` — custom Python import system for Ansible collections (~13.7k tokens). Installs meta path finders so `import ansible_collections.ns.name` works across multiple filesystem roots. Used by both ansible-core and ansible-test.
- `encrypt.py` — password hashing via passlib or stdlib crypt. `do_encrypt()` is the main entry point.
- `vars.py` — `combine_vars()` for merging variable dicts with configurable merge behavior (replace vs recursive merge).
- `plugin_docs.py` — plugin documentation extraction and formatting (~4k tokens).
- `unsafe_proxy.py` — `AnsibleUnsafeText`/`AnsibleUnsafeBytes` wrappers that mark strings as untrusted for Jinja2 templating.
- `path.py` — path utilities: `unfrackpath()` (normalize/resolve), `makedirs_safe()`, temp file cleanup.
- `singleton.py` — `Singleton` metaclass used by `Display` and other single-instance classes.
- `ssh_functions.py` — SSH key checking and host key management.

## Contracts

- `Display` is a singleton. Get it via `Display()` anywhere; all calls share state.
- `collection_loader` must remain compatible with all Python versions supported on both controller and remote (used by ansible-test import sanity). No non-stdlib imports allowed in its code.
- `combine_vars()` behavior depends on `DEFAULT_HASH_BEHAVIOUR` config: "replace" (default) or "merge" (recursive).
- `unsafe_proxy` types must pass through Jinja2 without being auto-escaped but also without being treated as trusted template content.

## Pitfalls

- `getuser()` fallback error handling was broken (commit 4184d96). When `getpass.getuser()` fails, the fallback must not raise a secondary exception.
- Post-fork deadlock: early Python writers (like pydevd debugger) can deadlock the logging system after `os.fork()` (commit 1d1bbe3). Display uses fork-safe locking.
- `deprecated()` calls require a `help_text` argument as of recent versions (commit ea7ad90). Old-style calls without it will fail.
- `PluginInfo` was switched to use `PluginType` enum (commit 43c0132). Code creating `PluginInfo` objects must use the enum, not raw strings.
- `_collection_finder.py` comment warns: "DO NOT add new non-stdlib import deps here." This file is loaded by external tools (ansible-test import sanity) in restricted environments.
