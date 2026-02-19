# Tests

Test infrastructure using ansible-test (not pytest directly).

## Structure

- `test/units/` — mirrors `lib/ansible/` structure, pytest-style
- `test/integration/targets/` — each target is a directory with tasks/runme.sh
- `test/sanity/` — ignore files and code-smell scripts

## Running tests

```bash
# Unit (single file)
ansible-test units -v --docker default test/units/modules/test_command.py

# Integration (needs distro container)
ansible-test integration -v --docker ubuntu2404 setup_remote_tmp_dir

# Sanity
ansible-test sanity -v --docker default --test pep8
```

## Contracts

- Unit tests: prefer functional tests over heavy mocking
- Integration targets are named after the feature being tested
- Container: `--docker default` for sanity/units, distro containers for integration
- Available containers listed in `test/lib/ansible_test/_data/completion/docker.txt`

## Pitfalls

- `ansible-test` wraps pytest with its own discovery — don't run pytest directly
- Integration tests may need specific OS features — wrong container = mysterious failures
- Some sanity tests (validate-modules) parse module source via AST — dynamic DOCUMENTATION blocks break them
