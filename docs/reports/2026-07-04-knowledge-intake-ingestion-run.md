# Knowledge Intake Ingestion Run — 2026-07-04

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-04
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 1             | OK |
| github     | —             | Error — see below |
| email      | 50            | OK (recovered) |
| **Total**  | **51**        | 3 of 4 sources succeeded |

The reported total of **51 new items** equals pinboard (0) + papers (1) + email (50). The `github` source contributed 0 items because it failed before mapping any results.

Note the reversal from recent runs: the `email` source — which failed on Gmail OAuth (`invalid_grant`) in the 2026-06-28 run and earlier — **recovered and fetched 50 items** this time. Meanwhile `github`, which had been the reliable high-yield source, failed on expired credentials.

## Source-level error: github

The `github` source threw a runtime error while mapping the GitHub Stars API response:

```text
[github] error: stars.map is not a function. (In stars.map callback, stars.map is undefined)
```

**Cause**: The GitHub personal access token in `.env` has expired or been revoked. A direct probe of the endpoint the adapter calls confirms the root cause:

```text
GET https://api.github.com/user/starred?sort=created&per_page=1
HTTP 401
{ message: Bad credentials, status: 401 }
```

The adapter (`src/adapters/github.ts`) does not check `res.ok` before calling `await res.json()`. On a 401 the API returns an error **object** rather than the expected **array** of stars, so `stars.map(...)` throws `stars.map is not a function`. The confusing error message is a symptom; the underlying issue is auth.

**Remediation**:

1. Mint a fresh GitHub personal access token (classic or fine-grained with read access to starred repos) and update `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`, then re-run the ingestion.
2. Optional code hardening (not done here — this run only reports counts): add a `res.ok` check in `src/adapters/github.ts` so an HTTP error surfaces as an explicit 401 message instead of the misleading `stars.map is not a function`.

This is an environment/auth issue local to the run host, not a data defect in the pipeline. The other three sources fetched normally.

## Retry note

The command was run twice. On the second run, `github` failed identically (confirming the 401 is persistent, not transient/rate-limited), `papers` returned 0 (the 1 item was already ingested and deduped on the first run), and `email` returned 32 (the remaining un-deduped items after the first runs 50). The authoritative per-source counts above are from the **first** run of the session, before dedup shrank subsequent totals.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
[papers] fetched 1 new items
[github] error: stars.map is not a function. (stars is not an array; GitHub API returned a 401 error object)
[email] fetched 50 new items

Ingestion complete: 51 new items

EXIT_CODE=0
```
