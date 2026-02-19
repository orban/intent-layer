# Parsing

Data loading, YAML processing, and vault encryption.

## Key components

- `dataloader.py` — main data loader, reads YAML/JSON files with vault decryption
- `vault/` — Ansible Vault: AES256 encryption for secrets in playbooks
- `yaml/` — custom YAML loader with Jinja2 support and line number tracking
- `mod_args.py` — module argument parsing (free-form vs key=value vs dict)

## Contracts

- YAML loader preserves line numbers for error reporting
- Vault-encrypted strings are transparently decrypted during loading
- Jinja2 expressions in YAML values are preserved as-is (evaluated later by the templating engine)
- `mod_args.py` handles the three module argument formats: `command: foo`, `command: key=val`, and dict form

## Pitfalls

- The custom YAML loader doesn't support all YAML spec features — designed for Ansible's subset
- Vault operations require a vault password/identity — missing it causes silent failures in some codepaths
