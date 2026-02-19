# CLI

Command-line entry points for all `ansible-*` commands.

## Commands

| File | Command | Purpose |
|------|---------|---------|
| `adhoc.py` | `ansible` | Run single tasks against hosts |
| `playbook.py` | `ansible-playbook` | Execute playbooks |
| `galaxy.py` | `ansible-galaxy` | Install/manage collections and roles (largest CLI, ~23k tokens) |
| `doc.py` | `ansible-doc` | Browse module/plugin documentation |
| `vault.py` | `ansible-vault` | Encrypt/decrypt files |
| `config.py` | `ansible-config` | View/dump configuration |
| `console.py` | `ansible-console` | Interactive REPL |
| `inventory.py` | `ansible-inventory` | Inspect inventory |
| `pull.py` | `ansible-pull` | Pull playbooks from VCS and run locally |

## Entry points

- `__init__.py` — shared base class `CLI`. Also handles `SSH_ASKPASS` interception (when invoked with specific env var, delegates to `_ssh_askpass.py` before any other imports).
- `arguments/option_helpers.py` — shared argparse option definitions used across all CLI commands.
- `scripts/` — shell wrapper entry points.

## Contracts

- Python >= 3.12 on controller (enforced in `__init__.py` via `_PY_MIN`)
- UTF-8 locale required (checked at import time by `initialize_locale()`)
- Blocking I/O required on stdin/stdout/stderr (checked by `check_blocking_io()`)
- All CLI classes inherit from the base `CLI` class in `__init__.py`

## Pitfalls

- `ansible-doc` crashes when scanning collections whose path contains `ansible_collections` twice (commit c6d8d20).
- `ansible-galaxy` must strip internal paths when using `AnsibleCollectionConfig.collection_paths` (commit 945516c).
- `ansible-pull` has output inconsistencies with `--check` on changed status (commit 4bc4030).
- `ansible-config` must serialize galaxy server config to proper JSON format, not Python repr (commit 2a4b1c8).
- Askpass prompts are limited to a single attempt. The `SSH_ASKPASS` shm-based mechanism in `__init__.py` bypasses normal CLI initialization.
