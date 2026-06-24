# Knowledge Intake Ingestion Run — 2026-06-24

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-24
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (all sources succeeded)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 6             | OK |
| papers     | 0             | OK |
| github     | 100           | OK |
| email      | 49            | OK |
| **Total**  | **155**       | 4 of 4 sources succeeded |

The reported total of **155 new items** equals pinboard (6) + papers (0) + github (100) + email (49).

## Source-level errors

None. Every source completed successfully this run.

Notably, the `email` source — which failed in the 2026-06-14 run due to a macOS Keychain timeout reading the Gmail OAuth token via the `gog` CLI — fetched 49 items cleanly this time. No keyring permission prompt blocked the run, so the prior environment/auth issue did not recur.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 6 new items
[papers] fetched 0 new items
[github] fetched 100 new items
[email] fetched 49 new items

Ingestion complete: 155 new items

EXIT_CODE=0
```
