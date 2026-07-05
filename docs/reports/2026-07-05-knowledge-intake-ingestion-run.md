# Knowledge Intake Ingestion Run — 2026-07-05

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-05
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 44            | OK |
| **Total**  | **44**        | 3 of 4 sources succeeded |

The reported total of **44 new items** comes entirely from the `email` source. The `github` source contributed 0 items because it failed before any items could be built.

## Source-level error: github

The `github` source failed while mapping the starred-repos response:

```text
[github] error: stars.map is not a function. (stars.map is undefined)
```

**Cause**: The GitHub personal access token is no longer valid. A direct probe of the starred-repos endpoint confirms it:

```text
$ curl -H "Authorization: Bearer $GITHUB_TOKEN" "https://api.github.com/user/starred?per_page=1"
HTTP 401
{
  "message": "Bad credentials",
  "documentation_url": "https://docs.github.com/rest",
  "status": "401"
}
```

The adapter does not check `res.ok` before calling `.json()`, so on a 401 it parses the error body (an object, not an array) and then calls `.map()` on it — producing the misleading `stars.map is not a function` message instead of surfacing the underlying 401. This is the known unprotected error path in the GitHub adapter.

**Remediation**:

1. Mint a fresh GitHub personal access token with the scopes the adapter needs (reading starred repos), update `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`, and re-run the ingestion.
2. (Code hardening, out of scope for this run) Have the GitHub adapter check `res.ok` and throw a clear auth error before parsing the body, so a 401 reports as "GitHub 401 Bad credentials".

This is an environment/auth issue local to the run host (an expired/revoked token), not a data defect. The other three sources ran normally, and `email` recovered — it fetched 44 items this run after the OAuth failure observed on 2026-06-28.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
[papers] fetched 0 new items
[github] error: stars.map is not a function. (stars.map is undefined)
[email] fetched 44 new items

Ingestion complete: 44 new items

EXIT_CODE=0
```
