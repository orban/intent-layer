# Galaxy

Client-side logic for Ansible Galaxy: installing, building, and managing collections and roles.

## Structure

- `api.py` — Galaxy REST API client. Handles v2/v3 API versions, authentication (token, client credentials), pagination, and server fallback.
- `collection/` — collection management (install, download, verify, build)
  - `__init__.py` — main collection operations (~19k tokens, largest file). Install, download, verify signatures, build tarballs.
  - `concrete_artifact_manager.py` — resolves collection artifacts from Galaxy servers, URLs, local paths, or git repos
  - `galaxy_api_proxy.py` — wraps multiple Galaxy servers with fallback
  - `gpg.py` — GPG signature verification for collections
- `dependency_resolution/` — resolves collection version constraints using `resolvelib`
  - `dataclasses.py` — `Candidate`, `Requirement` types for the resolver
- `role.py` — legacy role management (install from Galaxy or git)
- `token.py` — Galaxy API token handling (keyring, file, config)
- `user_agent.py` — user-agent string construction

## Contracts

- Collections use `resolvelib` for dependency resolution. The resolver operates on `Candidate` and `Requirement` objects from `dependency_resolution/dataclasses.py`.
- Galaxy API responses may omit the `results` key in cached responses. Always check for it (commit 192948434c).
- Collection metadata lives in `galaxy.yml` / `MANIFEST.json`. Schema validation uses data from `data/collections_galaxy_meta.yml`.
- `download_url` values may lack a scheme:host prefix (commit 390e112). URL handling must account for relative paths.

## Pitfalls

- Collection install can have metadata/filesystem location mismatch (commit 1e31c7c). The installed path may not match the namespace.name in metadata.
- `client_secret` and `access_token` config fields produce errant warnings if both are present (commit 183c695).
- When `ansible_collections` appears twice in a path, `ansible-doc` crashes during collection scanning (commit c6d8d20 in cli).
- Internal collection paths must be stripped from `AnsibleCollectionConfig.collection_paths` in user-facing output (commit 945516c).
- The v1 source info schema validation expects specific argument spec structure (commit 612d54f).
