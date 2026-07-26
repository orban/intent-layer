# Knowledge Intake Ingestion Run — 2026-07-26

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-26
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; three sources errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 0             | Error — EINTR scandir (new) |
| github     | 0             | Error — masked 401 (known) |
| email      | 0             | Error — OAuth invalid_grant (regression) |
| **Total**  | **1**         | 1 of 4 sources succeeded |

The worst run on record: only pinboard delivered, and only 1 item. The other three sources all failed before fetching anything, each for a different reason.

## Source-level errors

### papers — EINTR on iCloud scandir (new failure mode)

```text
[papers] error: EINTR: interrupted system call, scandir /Users/ryo/Library/Mobile Documents/com~apple~CloudDocs/Papers
```

**Cause**: The papers adapter scans an iCloud Drive folder, and the `scandir` syscall was interrupted (`EINTR`) — almost certainly by the iCloud/`fileproviderd` daemon materializing or syncing files in that directory at the moment of the scan. This is the first time this source has failed in any recorded run; it is transient, not a credential or code-logic issue.

**Remediation**: Re-run the ingestion — a retry will almost certainly succeed. For durability, the adapter could wrap the directory scan in an EINTR retry loop (retry the `scandir` on `EINTR` up to a few times), which is the standard handling for interruptible syscalls against iCloud-backed paths.

### github — masked 401 from expired token (known bug, day 22)

```text
[github] error: stars.map is not a function. (In stars.map(...), stars.map is undefined)
```

(The adapter dumps the full arrow-function source in the error; elided here for brevity.)

**Cause**: Same defect documented since the 2026-07-12 run. The GitHub token expired on 2026-07-04. The adapter never checks `response.ok`, so the 401 error body (a JSON object, not an array) flows into `stars.map(...)` and surfaces as a `TypeError` instead of an auth error. The source has now been dark for 22 days.

**Remediation**:

1. Rotate the GitHub token in `~/dev/knowledge-intake/.env` (a classic PAT with `read:user` scope, or fine-grained equivalent).
2. Fix the adapter to check `response.ok` (and ideally `Array.isArray(stars)`) before mapping, so an expired token reports as `401 Unauthorized` rather than `stars.map is not a function`.

### email — Gmail OAuth invalid_grant (regression)

```text
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-24": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth refresh token has been expired or revoked again. This is a regression: the same `invalid_grant` failure blocked email from at least 2026-05-23 through 2026-06-28, was re-authenticated around 2026-07-18, and the source then ran healthily through 2026-07-24 (draining backlog at the Gmail API's 50-item pagination cap per run). The search window in the failing query (`after:2026-07-24`) confirms the token worked on the 07-24 run and died sometime in the last two days. If the OAuth client is in Google's "Testing" publishing status, refresh tokens auto-expire after 7 days — that timeline fits the ~6 days between the 07-18 re-auth and now, and would explain why this keeps recurring.

**Remediation**:

1. Re-authenticate `gog` (`gog auth login`) from an interactive terminal to mint a fresh token.
2. To stop the recurrence, check the OAuth consent screen's publishing status for the `gog` client — moving it from "Testing" to "In production" (or using an app type without the 7-day refresh-token expiry) would make the re-auth stick.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-05-23 | 20 | 9 | 100 | 0 (err) | 129 | email: invalid_grant |
| 2026-05-25 | 0 | 0 | 100 | 0 (err) | 100 | email: invalid_grant |
| 2026-06-14 | 0 | 0 | 100 | 0 (err) | 100 | email: invalid_grant |
| 2026-06-28 | 0 | 0 | 100 | 0 (err) | 100 | email: invalid_grant |
| 2026-07-24 | 4 | 1 | 0 (err) | 50 | 55 | github dark; email at 50-item cap |
| **2026-07-26** | **1** | **0 (err)** | **0 (err)** | **0 (err)** | **1** | worst run on record |

(Reports for the 2026-07-12 → 2026-07-24 runs live on their own stacked `nightshift/knowledge-ingest-report-*` branches, not yet merged to main; the 07-24 figures above are from PR #71.)

Trends:

- **Source reliability has fully inverted since June.** Through 2026-06-28, github was the workhorse (100 items every run, likely at its own pagination cap) and email was dead. In July, github went dark (token expired 2026-07-04) while email recovered and drained at 50/run. Today neither works.
- **Email's OAuth token died again ~6 days after re-auth**, matching the 7-day refresh-token expiry of Google OAuth clients in "Testing" status. Until the client is published to production, expect this failure to recur weekly.
- **The github masked-401 bug remains unfixed after 5 consecutive reported runs.** Both the token rotation and the `response.ok` check are still outstanding.
- **Papers' EINTR failure is new and transient** — unlike the other two errors, it needs no credential work, just a retry (and ideally an EINTR retry loop in the adapter).
- **Backlog risk**: with email dead again and its 50-item-per-run cap, any newsletter backlog accumulated during the outage will take multiple healthy runs to drain once re-authenticated.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
[papers] error: EINTR: interrupted system call, scandir /Users/ryo/Library/Mobile Documents/com~apple~CloudDocs/Papers
[github] error: stars.map is not a function. (In stars.map(...), stars.map is undefined) [full arrow-function source elided; see .knowledge-ingest-2026-07-26.log for the verbatim dump]
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-24": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."

Ingestion complete: 1 new items

EXIT_CODE=0
```
