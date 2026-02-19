# Config

Configuration system for ansible-core. All settings are defined declaratively in YAML.

## Files

- `base.yml` — the single source of truth for all ansible configuration settings (~2260 lines). Each entry defines name, description, type, default, env vars, ini options, and version_added.
- `ansible_builtin_runtime.yml` — maps built-in plugin routing (redirects, deprecations, tombstones for removed plugins)
- `manager.py` — `ConfigManager` class that loads `base.yml`, resolves values from env/ini/cli/vars with precedence, and performs type coercion via `ensure_type()`
- `__init__.py` — re-exports

## How configuration resolution works

1. Plugin or CLI code requests a config value by name
2. `ConfigManager` checks sources in precedence order: variable → CLI arg → env var → ini file → default
3. `ensure_type()` coerces the raw value to the declared type (str, bool, int, float, list, dict, path, pathlist, pathspec, tmppath)
4. Vaulted values are decrypted transparently during coercion

## Contracts

- All new settings go in `base.yml`, nowhere else. The declarative schema is the API.
- Galaxy server definitions use a separate schema (`GALAXY_SERVER_DEF` in `manager.py`) with fields: url, username, password, token, auth_url, validate_certs, client_id, client_secret, timeout.
- Type coercion supports these types: `str`, `bool`, `boolean`, `int`, `integer`, `float`, `list`, `none`, `path`, `tmppath`, `pathspec`, `pathlist`, `dict`
- `INTERNAL_DEFS` defines settings only available to internal callers (e.g., lookup `_terms`)

## Pitfalls

- `ensure_type` must handle vaulted (encrypted) values. Values matching `_EncryptedStringProtocol` get decrypted before coercion (commit 9a426fe).
- `auto_silent*` interpreter discovery options were removed (commit 790b66f). Don't reference them.
- Config lookup with `show_origin` had bugs around variable resolution (commit 1cb2932).
- Galaxy server config dump must produce valid JSON, not Python dict repr (commit 2a4b1c8).
- The `NativeEnvironment` from Jinja2 is used for config value interpolation, so Jinja expressions in config values are evaluated.
