# Knowledge Intake Ingestion Run — 2026-07-17

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-17 (02:02 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)
- **Database**: `intake.db` at the repo root, mtime `2026-07-17 02:02` local — confirms the run wrote to the store

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 0             | Error — see below |
| **Total**  | **1**         | 2 of 4 sources succeeded |

The reported total of **1 new item** comes entirely from pinboard. Papers ran cleanly but had nothing new. GitHub and email both failed before fetching anything.

## Source-level errors

### github: `stars.map is not a function`

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known error-masking bug in the GitHub adapter, recurring since 2026-07-04. The GitHub API returns an HTTP 401 (expired/revoked token) with a JSON error object instead of an array of starred repos. The adapter never checks `response.ok` or validates the payload shape, so the auth failure surfaces as a `TypeError` when it calls `.map()` on the error object.

**Remediation**:

1. Rotate the GitHub token referenced in `~/dev/knowledge-intake/.env` and re-run.
2. Fix the adapter to check the HTTP status before parsing, so a 401 reports as an auth error rather than a `TypeError` (upstream fix in `knowledge-intake`, out of scope for this report).

### email: Gmail OAuth `invalid_grant`

```text
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?...&q=label%3ANewsletters+after%3A2026-07-15": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth refresh token used by the `gog` CLI has expired or been revoked. Same failure mode as the 2026-06-28 and 2026-07-16 runs — the token is read fine but rejected by Google's token endpoint.

**Remediation**: Re-authenticate `gog` from an interactive terminal (`gog auth login`), complete the Google consent screen, then re-run the ingestion.

Both failures are environment/auth issues local to the run host (plus the adapter's error-masking defect), not new code defects in the ingestion pipeline.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-06-28 | 0 | 0 | 100 | 0 (err) | 100 | github healthy; email `invalid_grant` |
| 2026-07-16 | 6 | 1 | 0 (err) | 0 (err) | 7 | github 401-masking; email `invalid_grant` |
| 2026-07-17 | 1 | 0 | 0 (err) | 0 (err) | 1 | same two failures as 07-16 |

Pinboard and papers remain the only live channels; both are healthy but low-volume day-to-day. GitHub has been down since its token expired (masked as the `stars.map` TypeError since 2026-07-04), and email regressed to `invalid_grant` on 2026-07-16 after a stable stretch. Neither credential has been rotated yet, so both failures repeated verbatim today.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
[papers] fetched 0 new items
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => {
      if (!latestStarred || starred_at > latestStarred)
        latestStarred = starred_at;
      const content = [
        repo.description ?? "",
        repo.language ? `Language: ${repo.language}` : "",
        repo.topics.length ? `Topics: ${repo.topics.join(", ")}` : "",
        `Stars: ${repo.stargazers_count}`
      ].filter(Boolean).join(`
`);
      return {
        source: this.source,
        sourceId: String(repo.id),
        title: repo.full_name,
        url: repo.html_url,
        content,
        savedAt: starred_at
      };
    })', 'stars.map' is undefined)
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-15": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."

Ingestion complete: 1 new items

EXIT_CODE=0
```
