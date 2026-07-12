# Knowledge Intake Ingestion Run — 2026-07-12

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-12
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 2             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 15            | OK |
| **Total**  | **17**        | 3 of 4 sources succeeded |

The reported total of **17 new items** equals pinboard (2) + papers (0) + email (15). The `github` source contributed 0 items because it failed before producing any.

## Source-level error: github

The `github` source failed with a TypeError while mapping the starred-repos response:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known 401-masking bug in the GitHub adapter, seen consistently since the 2026-07-04 run. The GitHub API token is expired or invalid, so the API returns an HTTP 401 JSON error object instead of an array. The adapter calls `stars.map(...)` on the response body without first checking the HTTP status, so the auth failure surfaces as a runtime TypeError rather than an authentication error.

**Remediation**:

1. Rotate the GitHub token used by the ingestion (`GITHUB_TOKEN` in `~/dev/knowledge-intake/.env` or the configured adapter credential) and re-run.
2. Fix the adapter (in the `knowledge-intake` repo, not this one): check `response.ok` / HTTP status before parsing and mapping the body, and surface a clear GitHub-auth-failed error instead of the misleading TypeError.

## Email source recovered

The `email` source, which failed on 2026-06-28 with an `invalid_grant` Gmail OAuth error, fetched normally this run (15 items) — consistent with the 2026-07-11 run (50 items). The alternating credential-failure pattern between GitHub and Email continues: Email is currently healthy, GitHub is currently broken.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 2 new items
[papers] fetched 0 new items
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
[email] fetched 15 new items

Ingestion complete: 17 new items

EXIT_CODE=0
```
