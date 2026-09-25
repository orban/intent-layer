# Knowledge Intake Ingestion Run — 2026-08-04

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-04 (02:01 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 3             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — recurring `stars.map` TypeError |
| email      | 0             | Error — Gmail OAuth `invalid_grant` |
| **Total**  | **4**         | 2 of 4 sources succeeded |

The reported total of **4 new items** equals pinboard (3) + papers (1). The two failing sources contributed 0 items because they errored before fetching.

Database write corroborated: `~/dev/knowledge-intake/intake.db` mtime is `Aug 4 02:01:19 2026`, matching the run window.

## Source-level error: github

The github adapter failed with `TypeError: stars.map is not a function` (see raw log below).

**Cause**: Recurring adapter bug, present in every run since 2026-07-04. The GitHub API returns a 401 (expired or invalid token), the adapter does not check the response status, and the error JSON object reaches `stars.map`, producing this misleading TypeError. Upstream bug in `knowledge-intake` — documented here, not fixed as part of this run.

**Remediation**: Refresh the GitHub token in the `knowledge-intake` `.env`, and ideally patch the adapter to check `response.ok` before mapping so auth failures surface as auth failures.

## Source-level error: email

The email adapter failed with a Gmail OAuth `invalid_grant` error — token expired or revoked (see raw log below).

**Cause**: The Gmail OAuth refresh token is invalid again. This failure mode oscillates: the same `invalid_grant` error appeared on 2026-06-28, email then worked on 2026-08-01 through 2026-08-03 (40, 21, and 39 items respectively), and the token is rejected again as of tonight.

**Remediation**: Re-authenticate `gog` from an interactive terminal, complete the Google consent screen, then re-run the ingestion. The email source pages at 50 items per run, so after re-auth the first run may return exactly 50 — a count of exactly 50 means backlog remains.

## Comparison with prior runs

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-08-01 | 0        | 1      | error  | 40    | 41 |
| 2026-08-02 | 3        | 0      | error  | 21    | 24 |
| 2026-08-03 | 0        | 0      | error  | 39    | 39 |
| 2026-08-04 | 3        | 1      | error  | error | **4** |

The github adapter has now failed identically in every run since 2026-07-04. Email regressed tonight after three working runs.

## Raw log

```text
[pinboard] fetched 3 new items
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
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-08-02": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."

Ingestion complete: 4 new items
```

Full log saved at `.knowledge-ingest-2026-08-04.log` in the `intent-layer` repo root.
