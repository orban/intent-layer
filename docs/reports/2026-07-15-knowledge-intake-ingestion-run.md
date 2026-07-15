# Knowledge Intake Ingestion Run — 2026-07-15

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-15
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 3             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 42            | OK |
| **Total**  | **45**        | 3 of 4 sources succeeded |

The reported total of **45 new items** equals pinboard (3) + papers (0) + email (42). The `github` source contributed 0 items because it failed before mapping results.

## Source-level error: github

The `github` source failed while mapping the starred-repos response:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known adapter bug first seen on 2026-07-04. When the GitHub API returns HTTP 401 (expired or revoked token), the response body is an error object rather than an array, and the adapter calls `.map()` on it without checking the status code. The real failure — authentication — is masked as a `TypeError`.

**Remediation**:

1. Refresh the GitHub token used by the ingestion (check `.env` in `~/dev/knowledge-intake` for the token variable) — the token has been rejected since 2026-07-04.
2. Fix the adapter to check `response.ok` / status code before mapping, so auth failures surface as HTTP errors instead of `TypeError`s. (Tracked as a recurring issue; out of scope for this run.)

Note the alternating credential pattern across runs: on 2026-06-28 the `email` source failed with an expired Gmail OAuth token while `github` fetched 100 items; on this run `email` fetched 42 items while `github` failed with an expired token. Email auth has recovered; GitHub auth has been broken since 2026-07-04.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 3 new items
[papers] fetched 0 new items
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => {
      if (!latestStarred || starred_at > latestStarred)
        latestStarred = starred_at;
      ...
    })', 'stars.map' is undefined)
[email] fetched 42 new items

Ingestion complete: 45 new items

EXIT_CODE=0
```
