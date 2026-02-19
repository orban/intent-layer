# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ansible-core (v2.21.0.dev0) — the engine behind Ansible. Python >= 3.12 on the controller; modules support down to Python 3.9 on targets. Licensed GPL-3.0-or-later, except `lib/ansible/module_utils/` which is BSD-2-Clause.

## Testing

Run only the specific test file relevant to the bug, not the full test suite. For example:

```bash
pytest test/units/modules/test_specific.py -x --tb=short
pytest test/units/modules/test_specific.py::TestClassName::test_method
```

Unit tests live in `test/units/`, mirroring the `lib/ansible/` structure.

## Architecture

### Module isolation boundary

The most important architectural rule: **modules execute on remote targets**, so `lib/ansible/modules/` can only import from `lib/ansible/module_utils/`. And `module_utils` cannot import from outside itself. This boundary is enforced by the AnsiballZ packaging system that bundles modules for remote execution.

### Code layout

- `lib/ansible/cli/` — CLI entry points (ansible, ansible-playbook, ansible-galaxy, etc.)
- `lib/ansible/executor/` — core execution engine: runs plays, tasks, manages workers
- `lib/ansible/playbook/` — data structures for plays, blocks, tasks, roles
- `lib/ansible/plugins/` — plugin framework (action, connection, callback, filter, lookup, strategy, become, cache, inventory)
- `lib/ansible/modules/` — built-in modules (apt, copy, file, git, user, etc.)
- `lib/ansible/module_utils/` — shared utilities shipped to targets with modules
- `lib/ansible/inventory/` — host/group inventory management
- `lib/ansible/parsing/` — data loading, YAML, vault encryption
- `lib/ansible/config/` — configuration system; `base.yml` defines all settings
- `lib/ansible/_internal/` — private API (templating engine, datatag system, JSON profiles, SSH agent, AnsiballZ builder). Not for external use.
- `lib/ansible/galaxy/` — ansible-galaxy client and dependency resolution

### Plugin system

Plugins live in `lib/ansible/plugins/<type>/`. Each type has its own base class in `__init__.py`. Action plugins run on the controller and typically wrap a module (e.g., `action/copy.py` handles local file transfer then invokes the `copy` module on the target).

### Test layout

- `test/units/` — mirrors `lib/ansible/` structure. Pytest-style, prefer functional tests over heavy mocking.
- `test/integration/targets/` — each target is a directory with tasks, runme.sh, or both. Named after the feature being tested.
- `test/sanity/` — ignore files and code-smell scripts for sanity tests.

## Code conventions

- Line limit: **160 characters** (not 80)
- E402 is ignored — in `lib/ansible/modules/`, imports come after the DOCUMENTATION/EXAMPLES/RETURN string blocks
- Use `from __future__ import annotations` for native type hints
- Modules require static DOCUMENTATION, EXAMPLES, and RETURN blocks as YAML strings (parsed via AST, cannot be dynamic)
- Modules must have a `main()` function and `if __name__ == '__main__':` guard
- Prefer stdlib over external dependencies

### Deprecation cycle

4 releases: deprecate in current, warn for 2 more, remove in the 4th. Use version from `lib/ansible/release.py` plus 3 (e.g., deprecating in 2.19 means removal in 2.22). Use `Display.deprecated` or `AnsibleModule.deprecate`.

## Changelog fragments

Every PR needs a fragment in `changelogs/fragments/`. Valid sections (from `changelogs/config.yaml`):

`major_changes`, `minor_changes`, `breaking_changes`, `deprecated_features`, `removed_features`, `security_fixes`, `bugfixes`, `known_issues`

Naming: `{issue_number}-{short-description}.yml` or `{component}-{description}.yml`. Never reuse existing fragment files. Format: YAML with section key mapping to a list of strings.

## PR and branch policy

- All PRs target `devel`
- New plugins belong in collections, not ansible-core
- Backwards compatibility is the top priority
- Bug fixes backported to latest stable only; critical fixes to latest + previous stable
- Security issues go to security@ansible.com, not GitHub

## CI

Azure Pipelines. Key jobs: Sanity (2 groups), Units (Python 3.9-3.14), Integration (various distros), Windows (2016/2019/2022/2025). Check CI failures with:

```bash
gh pr view <number> --comments     # ansibot posts failure details
gh pr checks <number>              # Azure Pipelines URLs
```
