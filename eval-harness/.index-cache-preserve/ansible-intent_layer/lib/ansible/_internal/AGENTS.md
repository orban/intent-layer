# _internal

Private controller-side internals. Everything here is unstable API, subject to change without notice.

## Subsystems

- `_templating/` — Jinja2 engine, lazy containers, marker handling, template variable resolution. The largest subsystem (~40k tokens). `_jinja_bits.py` contains filter/test registration; `_engine.py` is the core template evaluator.
- `_ansiballz/` — module packaging for remote execution. `_builder.py` manages extensions (debugpy, pydevd, coverage). `_wrapper.py` is the remote-side unpacker.
- `_datatag/` — type tagging system for tracking data provenance (trusted-as-template, origin tracking, encrypted string handling)
- `_json/` — JSON serialization profiles. `_profiles/` contains legacy, cache-persistence, and inventory-specific serializers.
- `_ssh/` — SSH agent management. `_ssh_agent.py` is a Python SSH agent client; `_agent_launch.py` handles agent process lifecycle.
- `_errors/` — error factory, alarm/task timeouts, captured exceptions, handler utilities
- `_encryption/` — crypt facade for password hashing
- `_plugins/` — internal plugin caching

## Entry points

- `__init__.py` — injects controller-side serialization map and import hook into `module_utils._internal`. The `setup()` function triggers side-effect imports.
- `_wrapt.py` — vendored wrapt (1.17.2) for decorator/proxy support

## Contracts

- This package augments `module_utils._internal` at import time by replacing stub functions with real implementations (e.g., `get_controller_serialize_map`, `import_controller_module`)
- `is_controller = True` flag distinguishes controller vs target context
- `@experimental` decorator marks types outside `_internal` that expose internal types

## Pitfalls

- Import order matters: `_internal.__init__` monkey-patches `module_utils._internal` on import. Disordered imports can break the controller detection mechanism (see DTFIX-FUTURE comment in `__init__.py`).
- Marker handling in Jinja templates is fragile. Multiple bug fixes for edge cases: macro invocations, filter results returning Marker, None values in template nodes, tuple slicing. Always test template changes against `test/units/template/`.
- AnsiballZ `sitecustomize` escaping: special characters in the wrapper need careful escaping (commit 6bb7bd7).
- `EncryptedString` redaction has multiple code paths. Changes to serialization must account for both tagged and untagged contexts.
