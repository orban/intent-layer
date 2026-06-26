# Knowledge Intake Ingestion Run — 2026-06-26

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-26
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; all four sources fetched cleanly)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 100           | OK |
| email      | 50            | OK |
| **Total**  | **150**       | 4 of 4 sources succeeded |

The reported total of **150 new items** equals pinboard (0) + papers (0) + github (100) + email (50).

## Notes

This run completed with no source-level errors. Notably, the `email` source — which failed in the prior runs (2026-05-23, 2026-05-25, and 2026-06-14) on a macOS Keychain token timeout in non-interactive mode — fetched 50 new items cleanly this time, meaning the Gmail OAuth token was available without an interactive Keychain prompt.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
[papers] fetched 0 new items
[github] fetched 100 new items
[email] fetched 50 new items

Ingestion complete: 150 new items

EXIT_CODE=0
```
