# Knowledge Intake Ingestion Run — 2026-06-30

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-30
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; all four sources succeeded)

## Per-source results

| Source     | Items fetched | Status |
|-----------|--------------:|--------|
| pinboard   | 3             | OK |
| papers     | 0             | OK |
| github     | 100           | OK |
| email      | 50            | OK |
| **Total**  | **153**       | 4 of 4 sources succeeded |

The reported total of **153 new items** equals pinboard (3) + papers (0) + github (100) + email (50).

## Email source recovered

The `email` source — which failed on the prior two runs (2026-06-28 and 2026-06-29) with a Gmail OAuth `invalid_grant` ("Token has been expired or revoked.") error — fetched 50 items cleanly this run. The Gmail OAuth token was re-authenticated since the last failure, restoring the source. No remediation is outstanding.

The `papers` source returned 0 items, consistent with prior runs; this reflects no new matching papers in the window rather than a failure.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 3 new items
[papers] fetched 0 new items
[github] fetched 100 new items
[email] fetched 50 new items
Ingestion complete: 153 new items

EXIT_CODE=0
```

## Operational follow-up

- The Gmail OAuth token is currently valid. If the `email` source fails again on a future run with `invalid_grant`, re-authenticate via `gog auth login` from an interactive terminal before re-running the ingestion.
