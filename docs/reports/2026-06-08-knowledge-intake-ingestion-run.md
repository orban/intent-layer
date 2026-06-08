# Knowledge Intake Ingestion Run — 2026-06-08

Operational run of the `knowledge-intake` ingestion pipeline, capturing observed fetch counts for each source and documenting the blocking Gmail auth failure.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-08
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0`
- **Run outcome**: Partial. Three sources emitted confirmed fetch counts; `email` failed before any `fetched N new items` line was emitted.

## Per-source results

| Source   | Items fetched | Status |
|----------|--------------:|--------|
| pinboard | 0             | OK |
| papers   | 0             | OK |
| github   | 100           | OK |
| email    | unknown       | Error — fetch did not complete |

Confirmed successful-source subtotal: **100** new items.

The CLI reported `Ingestion complete: 100 new items`, which matches the sum of the three successful sources: pinboard (0) + papers (0) + github (100). No confirmed fetch count was produced for `email`, so this run does **not** provide a complete per-source result for all configured sources.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): gmail options: token source: get token for ryan.orban@gmail.com: read token: keyring connection timed out after 10s while reading keyring item (macOS Keychain may be waiting for a permission prompt; run `gog auth list` from a terminal and click "Always Allow" when prompted); set GOG_KEYRING_BACKEND=file and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead
```

Follow-up validation on the same host reproduced the same Keychain timeout for:

- `gog auth list`
- direct Gmail search with `--account ryan.orban@gmail.com`
- direct Gmail search with `--account me@ryanorban.com`

That establishes this as a local noninteractive Keychain-access problem rather than a parsing/reporting issue in the ingestion CLI.

## Remediation needed for a complete rerun

To obtain a confirmed `email` fetch count, rerun after fixing `gog` token access by either:

1. Running `gog auth list` from an interactive macOS terminal session and approving the Keychain prompt with **Always Allow**.
2. Migrating `gog` to encrypted file-backed token storage by setting `GOG_KEYRING_BACKEND=file` and `GOG_KEYRING_PASSWORD=<password>`, then importing or reauthing the Gmail token before re-running ingestion.

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
