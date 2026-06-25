# Knowledge Intake Ingestion Run — 2026-06-25

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-25
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; all four sources fetched)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 1             | OK |
| github     | 100           | OK |
| email      | 50            | OK |
| **Total**  | **152**       | 4 of 4 sources succeeded |

The reported total of **152 new items** equals pinboard (1) + papers (1) + github (100) + email (50). Every source fetched cleanly this run — the `email` source, which timed out on a macOS Keychain prompt in the 2026-06-14 run, completed normally here.

## Source notes

- **github** returned 100 items, the same page-size ceiling seen on prior runs. When a source consistently reports exactly 100 it is worth confirming pagination is exhausting the backlog rather than capping at the first page; this run's count matched the prior baseline and was treated as expected.
- **email** recovered from the prior run's failure. The 2026-06-14 report documented a `gog` Gmail Keychain timeout (`keyring connection timed out after 10s`); no such error occurred this run, so the OAuth token read succeeded without an interactive prompt.

No source-level errors occurred during this run.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
[papers] fetched 1 new items
[github] fetched 100 new items
[email] fetched 50 new items

Ingestion complete: 152 new items

EXIT_CODE=0
```
