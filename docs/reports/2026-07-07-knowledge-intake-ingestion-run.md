# Knowledge Intake Ingestion Run — 2026-07-07

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-07
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 4             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 0             | Error — see below |
| **Total**  | **4**         | 2 of 4 sources succeeded |

The reported total of **4 new items** equals pinboard (4) + papers (0). The `github` and `email` sources contributed 0 items because each failed before persisting any records.

## Source-level error: github

The `github` source failed with a `TypeError` while mapping the starred-repos response:

```text
[github] error: stars.map is not a function. (In "stars.map(...)", "stars.map" is undefined)
```

**Cause**: This is a masked HTTP 401. The GitHub adapter calls `.map()` on the parsed response body without first checking the HTTP status. When the API returns `401 Bad credentials` (an expired or revoked personal access token), the body is an error object `{ message, documentation_url }` rather than an array, so `stars.map` is `undefined` and surfaces as a `TypeError` instead of an auth error. This is the same latent error-handling bug flagged in prior runs — the underlying failure is authentication, not a data-shape problem.

**Remediation**:

1. Refresh the GitHub personal access token used by the ingestion pipeline (check its expiry under GitHub Developer settings then Personal access tokens), update the value in `~/dev/knowledge-intake/.env`, and re-run.
2. Follow-up code fix (in `knowledge-intake`, not this repo): the GitHub adapter should check `response.ok`/status before calling `.map()` and raise a clear auth error on 401 rather than letting `stars.map is not a function` mask the real cause.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-06": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth token has expired or been revoked (`invalid_grant`). The token was read successfully from the Keychain but rejected by Googles token endpoint — the refresh token is no longer valid.

**Remediation**:

1. Re-authenticate `gog` to mint a fresh Gmail OAuth token: run `gog auth login` (or the projects documented re-auth flow) from an interactive terminal, complete the Google consent screen, then re-run the ingestion.
2. Confirm the account still grants the required Gmail scopes and that the OAuth client/app has not been revoked in the Google accounts security settings.

Both failures are environment/auth issues local to the run host (expired credentials), not defects in the ingestion orchestration. The `github` case additionally exposes a latent error-handling bug worth fixing so future 401s report as auth errors rather than a misleading `TypeError`.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 4 new items
[papers] fetched 0 new items
[github] error: stars.map is not a function. (In "stars.map(({ starred_at, repo }) => ...)", "stars.map" is undefined)
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?...&q=label%3ANewsletters+after%3A2026-07-06": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."

Ingestion complete: 4 new items

EXIT_CODE=0
```
