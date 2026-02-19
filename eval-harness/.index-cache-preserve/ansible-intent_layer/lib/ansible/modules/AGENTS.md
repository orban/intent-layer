# Modules

Built-in modules that execute on remote targets via AnsiballZ.

## Isolation boundary

Modules can ONLY import from `ansible.module_utils`. No other ansible imports allowed. This is the most important architectural rule — modules are packaged and shipped to remote machines.

## Module structure

Every module requires:
1. `DOCUMENTATION` — YAML string (parsed via AST, must be static)
2. `EXAMPLES` — YAML string with usage examples
3. `RETURN` — YAML string describing return values
4. `main()` function with module logic
5. `if __name__ == '__main__': main()` guard

## Contracts

- E402 is ignored — imports come after the doc blocks
- Use `AnsibleModule` from `ansible.module_utils.basic` for argument parsing
- Return results via `module.exit_json()` or `module.fail_json()`
- Check mode: implement `supports_check_mode=True` and test `module.check_mode`

## Key modules

- `command.py`, `shell.py` — run commands (command avoids shell, shell uses it)
- `copy.py` — file transfer (action plugin handles local→remote, module handles permissions)
- `file.py` — file/directory state management
- `apt.py`, `yum.py`, `dnf.py` — package managers
- `user.py`, `group.py` — user management
