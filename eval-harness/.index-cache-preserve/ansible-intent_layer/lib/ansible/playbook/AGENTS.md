# Playbook

Data structures representing Ansible playbook elements.

## Key classes

- `Playbook` — top-level container, holds list of `Play` objects
- `Play` — a play: hosts, tasks, roles, vars, handlers
- `Block` — groups tasks with rescue/always error handling
- `Task` — a single task with module, args, conditionals, loops
- `Role` — role abstraction with tasks, handlers, defaults, vars, files, templates
- `RoleDefinition` — role metadata and dependency resolution

## Data loading

All classes use `load()` class methods that parse YAML dicts into validated objects. Field validation happens through the attribute descriptor system.

## Contracts

- Plays contain Blocks, Blocks contain Tasks (not Tasks directly in Plays)
- Role dependencies are resolved recursively at load time
- Variable precedence: extra vars > task vars > block vars > role vars > play vars > inventory vars
- `when`, `loop`, `register`, `notify` are task-level attributes handled by the executor, not the playbook layer
