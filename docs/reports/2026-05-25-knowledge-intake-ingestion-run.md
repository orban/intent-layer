# Knowledge Intake Ingestion Run — 2026-05-25

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-05-25
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 100           | OK |
| email      | 0             | Error — see below |
| **Total**  | **100**       | 3 of 4 sources succeeded |

The reported total of **100 new items** equals pinboard (0) + papers (0) + github (100). The `email` source contributed 0 items because it failed before fetching.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): gmail options: token source: get token for ryan.orban@gmail.com: read token: keyring connection timed out after 10s while reading keyring item (macOS Keychain may be waiting for a permission prompt; run `gog auth list` from a terminal and click "Always Allow" when prompted); set GOG_KEYRING_BACKEND=file and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead
```

**Cause**: The macOS Keychain read for the Gmail OAuth token timed out after 10s. This happens when the Keychain is waiting on an interactive "Always Allow" permission prompt that never gets answered in a non-interactive run.

**Remediation** (either option):

1. Run `gog auth list` from an interactive terminal and click **Always Allow** when macOS prompts for Keychain access, then re-run the ingestion.
2. Switch `gog` to encrypted file-based token storage so no Keychain prompt is needed: set `GOG_KEYRING_BACKEND=file` and `GOG_KEYRING_PASSWORD=<password>` in the environment before running.

This is an environment/auth issue local to the run host, not a code defect in the ingestion pipeline. The other three sources fetched normally.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
[papers] fetched 0 new items
[github] fetched 100 new items
Ingestion complete: 100 new items
[email] error: gog gmail search failed (exit 1): gmail options: token source: get token for ryan.orban@gmail.com: read token: keyring connection timed out after 10s while reading keyring item (macOS Keychain may be waiting for a permission prompt; run `gog auth list` from a terminal and click "Always Allow" when prompted); set GOG_KEYRING_BACKEND=file and GOG_KEYRING_PASSWORD=<password> to use encrypted file storage instead

EXIT_CODE=0
```
