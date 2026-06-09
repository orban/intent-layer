# Knowledge Intake Ingestion Run - 2026-06-09

Operational run of the `knowledge-intake` ingestion pipeline, capturing the observed result for each source and preserving the raw source-level output.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-09
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored before returning a fetched count)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 100           | OK |
| email      | unavailable   | Error - see below |
| **Total observed from successful sources** | **100** | 3 of 4 sources returned counts |

The reported total of **100 new items** matches the successful source counts: pinboard (0) + papers (0) + github (100).

The `email` source did not return a fetched-item count. It failed during Gmail auth before any fetch result was emitted, so this run does not provide a numeric per-source count for `email`.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): gmail options: token source: get token for ryan.orban@gmail.com: read token: keyring connection timed out after 10s while reading keyring item (macOS Keychain may be waiting for a permission prompt; run `gog auth list` from a terminal and click "Always Allow" when prompted); set GOG_KEYRING_BACKEND=file and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead
```

**Cause**: The macOS Keychain read for the Gmail OAuth token timed out after 10s. This indicates the host was waiting for an interactive permission prompt that was not completed during the non-interactive run.

**Remediation**:

1. Run `gog auth list` from an interactive terminal and click **Always Allow** when macOS prompts for Keychain access, then re-run the ingestion.
2. Or set `GOG_KEYRING_BACKEND=file` and `GOG_KEYRING_PASSWORD=<password>` to use encrypted file-backed token storage before running the ingestion again.

This is a local environment/auth failure, not an observed ingestion code failure in the successful sources above.

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
