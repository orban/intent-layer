# Knowledge Intake Ingestion Run — 2026-06-23

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-23
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (all four sources succeeded)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 2             | OK |
| papers     | 0             | OK |
| github     | 100           | OK |
| email      | 50            | OK |
| **Total**  | **152**       | 4 of 4 sources succeeded |

The reported total of **152 new items** equals pinboard (2) + papers (0) + github (100) + email (50). Every source completed without error.

Notably, the `email` source — which failed on the 2026-06-14 run due to a macOS Keychain timeout reading the Gmail OAuth token via the `gog` CLI — fetched 50 items cleanly this run, so no remediation was needed.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 2 new items
[papers] fetched 0 new items
[github] fetched 100 new items
[email] fetched 50 new items

Ingestion complete: 152 new items

EXIT_CODE=0
```
