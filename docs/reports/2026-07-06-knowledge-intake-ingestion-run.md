# Knowledge Intake Ingestion Run — 2026-07-06

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-06
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 35            | OK |
| **Total**  | **35**        | 3 of 4 sources succeeded |

The reported total of **35 new items** equals pinboard (0) + papers (0) + email (35). The `github` source contributed 0 items because it threw before yielding any.

Note the reversal from the 2026-06-28 run: that run had github succeed (100 items) and email fail on an expired Gmail OAuth token. This run is the inverse — email recovered and fetched 35 items, while github failed.

## Source-level error: github

The `github` source threw while mapping the starred-repos response:

```text
[github] error: stars.map is not a function. (In stars.map(...), stars.map is undefined)
```

**Cause**: The GitHub adapter assumes the stars endpoint returns an array and calls `.map` on it directly. When the request fails — most commonly an expired/invalid token returning HTTP 401 with a JSON error object (a message of Bad credentials) instead of an array — `stars` is not an array, so `stars.map` is undefined and the adapter throws a `TypeError`. The underlying HTTP status and body are swallowed and surface only as this generic map-is-not-a-function message.

**Remediation**:

1. Refresh the GitHub token used by the ingestion pipeline (check the `GITHUB_TOKEN` or equivalent value in `~/dev/knowledge-intake/.env`), then re-run the ingestion. If the token is valid, confirm it still carries the scopes needed to read starred repositories.
2. Harden the GitHub adapter so a non-array response is detected before `.map` — check `response.ok` / `Array.isArray(stars)` and surface the real HTTP status and body. This turns a cryptic `TypeError` into an actionable `[github] error: 401 Bad credentials`.

Item 1 is an environment/auth issue local to the run host, not a pipeline defect. Item 2 is a latent code bug in the adapter error handling that masks the true cause; it is noted here for follow-up but not fixed in this reporting task. The other three sources ran normally.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
[papers] fetched 0 new items
[github] error: stars.map is not a function. (In stars.map(...), stars.map is undefined)
[email] fetched 35 new items

Ingestion complete: 35 new items

EXIT_CODE=0
```
