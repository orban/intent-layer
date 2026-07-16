# Knowledge Intake Ingestion Run — 2026-07-16

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-16 (02:03 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)
- **Database**: `~/dev/knowledge-intake/intake.db` mtime Jul 16 02:03:11 confirms the write

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 6             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — known 401-masking bug |
| email      | 0             | Error — Gmail OAuth expired again |
| **Total**  | **7**         | 2 of 4 sources succeeded |

The reported total of **7 new items** equals pinboard (6) + papers (1). Both github and email contributed 0 items because they failed before fetching — the first run on record where both auth-dependent sources are down simultaneously.

## Source-level error: github (recurring since 2026-07-04)

```text
[github] error: stars.map is not a function.
```

**Cause**: The known, still-unfixed adapter bug. The GitHub starred-repos request returns an HTTP 401 body (the token in `.env` is expired), and the adapter calls `.map()` on it without checking the response status. The TypeError masks the real failure: an expired GitHub token. Identical signature on every run since 2026-07-04. This is an upstream defect in `knowledge-intake` — documented here, not fixed here.

**Remediation** (upstream in `knowledge-intake`):

1. Rotate the GitHub token in `~/dev/knowledge-intake/.env`.
2. Validate HTTP status in the adapter before parsing, so auth failures surface as auth failures instead of a TypeError.

## Source-level error: email (regression)

```text
[email] error: gog gmail search failed (exit 1): ... oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth refresh token has expired or been revoked again (`invalid_grant`). The same failure hit 2026-06-28, recovered on its own by 2026-07-12, and held through 2026-07-15 (42 items fetched yesterday). Today it is back.

**Remediation**: Re-authenticate `gog` from an interactive terminal (e.g. `gog auth login`), confirm the Gmail scopes are still granted, then re-run the ingestion.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-06-28 | 0 | 0 | 100 | 0 (auth) | 100 |
| 2026-07-13 | 6 | 1 | 0 (bug) | 30 | 37 |
| 2026-07-14 | 5 | 0 | 0 (bug) | 30 | 35 |
| 2026-07-15 | 3 | 0 | 0 (bug) | 42 | 45 |
| 2026-07-16 | 6 | 1 | 0 (bug) | 0 (auth) | 7 |

The github source has failed every run since 2026-07-04. The email source had been healthy since 2026-07-12 and regressed today, leaving pinboard and papers as the only live channels.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 6 new items
[papers] fetched 1 new items
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

Ingestion complete: 7 new items

EXIT_CODE=0
```
