# Plugins

Controller-side plugin framework with multiple types.

## Architecture

Each plugin type lives in `plugins/<type>/` with its own base class in `__init__.py`.

### Plugin types
- **action** — run on controller, typically wrap a module (e.g., `action/copy.py` handles local file transfer then invokes `copy` module on target)
- **connection** — transport (ssh, local, docker, etc.)
- **callback** — event hooks for output/logging
- **filter** — Jinja2 filter plugins for templates
- **lookup** — data retrieval from external sources
- **strategy** — execution strategies (linear, free, debug)
- **become** — privilege escalation (sudo, su, etc.)
- **cache** — fact caching backends
- **inventory** — dynamic inventory sources

## Contracts

- Plugins must inherit from the type's base class
- Plugin loading uses a finder/loader system, not direct imports
- Action plugins are the bridge between controller and target — they prepare data, invoke the module, and process results
- New plugins should go in collections, not ansible-core

## Pitfalls

- Action plugins with the same name as a module automatically wrap that module
- Plugin base classes define required methods — must implement all abstract methods
- `_execute_module()` in action plugins handles AnsiballZ packaging transparently
