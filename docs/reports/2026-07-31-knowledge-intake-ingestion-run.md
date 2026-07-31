# Knowledge Intake Ingestion Run — 2026-07-31

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-31
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK (page-capped at 50) |
| **Total**  | **52**        | 3 of 4 sources succeeded |

The reported total of **52 new items** equals pinboard (1) + papers (1) + email (50). The `github` source contributed 0 items because it failed before producing any.

Persistence corroborated: `~/dev/knowledge-intake/intake.db` mtime is 2026-07-31 02:01:58, matching the run.

## Source-level error: github

The `github` source failed with the same error seen in every run since 2026-07-04:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This `TypeError` masks an HTTP 401 from the GitHub API — the token in `.env` is expired or revoked, the API returns an error object instead of an array, and the adapter calls `.map` on it without checking the response status. This is a known upstream bug in `knowledge-intake` (confirmed via a direct `curl` probe of `/user/starred` on 2026-07-28). The 0-item result is an auth failure, not an empty feed.

**Remediation**:

1. Rotate the GitHub token in `~/dev/knowledge-intake/.env`.
2. Upstream fix (out of scope for this run): the github adapter should check the HTTP status before treating the response body as an array, so auth failures surface as auth errors rather than `TypeError`.

## Email note

The `email` source recovered from its 2026-07-16 `invalid_grant` failure by 2026-07-28 and remains healthy. It fetched exactly 50 items, which is the page cap (`maxResults=50`) — a backlog likely remains and subsequent runs should continue draining it (the 2026-07-28 run also hit the cap).

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
[papers] fetched 1 new items
[github] error: stars.map is not a function. (truncated — full text in .knowledge-ingest-2026-07-31.log)
[email] fetched 50 new items
Ingestion complete: 52 new items

EXIT_CODE=0
```
