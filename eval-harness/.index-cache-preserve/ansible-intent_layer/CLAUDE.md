# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ansible-core (v2.21.0.dev0) — the engine behind Ansible. Python >= 3.12 on the controller; modules support down to Python 3.9 on targets. GPL-3.0-or-later, except `lib/ansible/module_utils/` which is BSD-2-Clause.

## Testing

Run only the specific test file relevant to the bug, not the full test suite. For example:

```bash
pytest test/units/modules/test_specific.py -x --tb=short
pytest test/units/modules/test_specific.py::TestClassName::test_method
```

Unit tests live in `test/units/`, mirroring the `lib/ansible/` structure.

## Architecture

### Module isolation boundary (CRITICAL)

Modules execute on remote targets. `lib/ansible/modules/` can ONLY import from `lib/ansible/module_utils/`. And `module_utils` cannot import from outside itself. Enforced by AnsiballZ packaging.

### Code layout

- `lib/ansible/cli/` — CLI entry points
- `lib/ansible/executor/` — execution engine, runs plays/tasks, manages workers
- `lib/ansible/playbook/` — data structures for plays, blocks, tasks, roles
- `lib/ansible/plugins/` — plugin framework (action, connection, callback, filter, lookup, strategy, become, cache, inventory)
- `lib/ansible/modules/` — built-in modules (apt, copy, file, git, user, etc.)
- `lib/ansible/module_utils/` — shared utilities shipped to targets
- `lib/ansible/parsing/` — YAML loading, vault encryption
- `lib/ansible/config/` — configuration system; `base.yml` defines all settings
- `lib/ansible/_internal/` — private API (templating, datatag, AnsiballZ)

## Contracts

- 160-char line limit (not 80)
- E402 ignored in modules — imports come after DOCUMENTATION/EXAMPLES/RETURN blocks
- `from __future__ import annotations` for type hints
- Modules require static DOCUMENTATION, EXAMPLES, RETURN blocks as YAML strings
- Modules must have `main()` and `if __name__ == '__main__':` guard
- Deprecation cycle: 4 releases (deprecate, warn ×2, remove)
- Every PR needs a changelog fragment in `changelogs/fragments/`
- All PRs target `devel` branch

## Pitfalls

- Container selection: `--docker default` for sanity/units only, distro containers for integration
- New plugins belong in collections, not ansible-core
- `base.yml` defines all configuration — don't add settings anywhere else
- Security issues go to security@ansible.com, not GitHub

## Downlinks

| Area | Node |
|------|------|
| Modules | `lib/ansible/modules/AGENTS.md` |
| Module Utils | `lib/ansible/module_utils/AGENTS.md` |
| Plugins | `lib/ansible/plugins/AGENTS.md` |
| Executor | `lib/ansible/executor/AGENTS.md` |
| Playbook | `lib/ansible/playbook/AGENTS.md` |
| Parsing | `lib/ansible/parsing/AGENTS.md` |
| CLI | `lib/ansible/cli/AGENTS.md` |
| Config | `lib/ansible/config/AGENTS.md` |
| Galaxy | `lib/ansible/galaxy/AGENTS.md` |
| Utils | `lib/ansible/utils/AGENTS.md` |
| Internals | `lib/ansible/_internal/AGENTS.md` |
| Tests | `test/AGENTS.md` |
