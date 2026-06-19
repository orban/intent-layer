# Knowledge Intake Ingestion Run — 2026-06-19

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-19
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Note on invocation**: the host shell is `fish`, which can't `source` a dotenv file. The command was run through `bash -c '…'` so `source .env` works; the command itself is otherwise verbatim.

## Per-source results

The pipeline prints `fetched N new items` per source, where **N is the raw number of records pulled from the API, not the number actually inserted**. Inserts are deduplicated downstream via `INSERT OR IGNORE` on `UNIQUE(source, source_id)` (see `src/db.ts`). The table below reports both the pipeline's printed count and the genuinely-new rows added to `intake.db`, verified by querying the database immediately after the run.

| Source     | Reported (printed) | Actually inserted | Status |
|------------|-------------------:|------------------:|--------|
| pinboard   | 0                  | 0                 | OK — no new items |
| papers     | 0                  | 0                 | OK — no new items |
| github     | 100                | **0**             | OK to run, but the 100 is re-surfaced, not new — see below |
| email      | 0                  | 0                 | Error — masked failure, see below |
| **Total**  | **100**            | **0**             | 3 of 4 sources ran; 0 genuinely new items |

The pipeline's headline "Ingestion complete: 100 new items" is the sum of the printed per-source counts (0 + 0 + 100 + 0). **No new items were actually persisted this run.**

## Data-quality caveat: github's "100 new items" is re-surfaced, not new

The printed `100` is misleading. It's the raw GitHub starred-repos page, all of which were already in the database.

Evidence from `intake.db`, queried right after the run:

- `github` holds **131 rows total**, and the most recent genuine insert was `2026-06-07T09:01:25Z` — 12 days before this run.
- Rows inserted for `github` in the 10 minutes around this run: **0**. Every one of the 100 fetched records was dropped by `INSERT OR IGNORE` as a duplicate.

Root cause in `src/adapters/github.ts`:

1. The adapter requests `per_page: "100"` with **no pagination loop**, so each run pulls at most the first 100 starred repos. 100 is a hard page cap, not a measure of new activity.
2. It sets a `since` cursor (`params.set("since", cursor)`), but GitHub's `GET /user/starred` endpoint **does not support a `since` query parameter** — it's silently ignored. With `sort=created` (default `desc`), every run therefore returns the same 100 most-recently-starred repos.
3. The cursor is still persisted (`setCursor` advanced it to `2026-06-02T18:05:18Z` this run), giving a false impression of progress while having no effect on what the API returns.

Net effect: `github` re-fetches the same page each run, prints `100`, and inserts 0. This matches the identical `100` seen in the 2026-06-14 run. To report genuinely-new counts, the pipeline should print post-dedup insert counts (e.g. the `changes` from the `INSERT OR IGNORE`) rather than `items.length`, and the adapter needs real pagination plus client-side filtering on `starred_at` (since `since` is a no-op for this endpoint).

## Source-level error: email (masked failure, not a genuine zero)

`email` reported 0 items, but this is a **failure masked as a zero**, not an empty fetch. It failed before fetching anything:

```text
[email] error: gog gmail search failed (exit 1): gmail options: token source: get token for ryan.orban@gmail.com: read token: keyring connection timed out after 10s while reading keyring item (macOS Keychain may be waiting for a permission prompt; run `gog auth list` from a terminal and click "Always Allow" when prompted); set GOG_KEYRING_BACKEND=file and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead
```

**Cause**: the macOS Keychain read for the Gmail OAuth token timed out after 10s, because the Keychain is waiting on an interactive "Always Allow" prompt that never gets answered in a non-interactive run.

**Confirmation it's a standing outage**: `email`'s last successful insert in `intake.db` is `2026-04-27T21:57:37Z`, and its cursor is frozen at `2026-04-27 14:15`. The source has been failing for ~7 weeks; every run since has logged the same Keychain timeout and recorded 0.

**Remediation** (either option):

1. Run `gog auth list` from an interactive terminal and click **Always Allow** when macOS prompts for Keychain access, then re-run the ingestion.
2. Switch `gog` to encrypted file-based token storage so no Keychain prompt is needed: set `GOG_KEYRING_BACKEND=file` and `GOG_KEYRING_PASSWORD=<password>` in the environment before running.

This is an environment/auth issue local to the run host, not a code defect in the ingestion pipeline.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
[papers] fetched 0 new items
[github] fetched 100 new items
[email] error: gog gmail search failed (exit 1): gmail options: token source: get token for ryan.orban@gmail.com: read token: keyring connection timed out after 10s while reading keyring item (macOS Keychain may be waiting for a permission prompt; run `gog auth list` from a terminal and click "Always Allow" when prompted); set GOG_KEYRING_BACKEND=file and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead

Ingestion complete: 100 new items

EXIT_CODE=0
```

## Database verification (post-run)

Queried `~/dev/knowledge-intake/intake.db` immediately after the run:

```text
per-source totals:
  pinboard  4737  (last fetch 2026-06-18T09:02:01Z)
  papers     755  (last fetch 2026-06-12T09:07:10Z)
  email      296  (last fetch 2026-04-27T21:57:37Z)  ← stale, source broken since
  github     131  (last genuine insert 2026-06-07T09:01:25Z)

github rows inserted during this run: 0
cursors: github → 2026-06-02T18:05:18Z (advanced, but has no effect on /user/starred)
         email  → 2026-04-27 14:15 (frozen)
```
