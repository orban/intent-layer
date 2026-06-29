# Knowledge Intake Ingestion Run — 2026-06-29

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-06-29
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 1             | OK |
| github     | 100           | OK |
| email      | 0             | Error — see below |
| **Total**  | **102**       | 3 of 4 sources succeeded |

The reported total of **102 new items** equals pinboard (1) + papers (1) + github (100). The `email` source contributed 0 items because it failed before fetching.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-06-26": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth token has expired or been revoked (`invalid_grant`). This is the same failure mode seen on the 2026-06-28 run: the token is read successfully but rejected by Google's token endpoint — the refresh token is no longer valid.

**Remediation**:

1. Re-authenticate `gog` to mint a fresh Gmail OAuth token: run `gog auth login` (or the project's documented re-auth flow) from an interactive terminal, complete the Google consent screen, then re-run the ingestion.
2. Confirm the account still grants the required Gmail scopes and that the OAuth client/app has not been revoked in the Google account's security settings.

This is an environment/auth issue local to the run host, not a code defect in the ingestion pipeline. The other three sources fetched normally.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
[papers] fetched 1 new items
[github] fetched 100 new items
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-06-26": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."

Ingestion complete: 102 new items

EXIT_CODE=0
```
