# Knowledge Intake Ingestion Run — 2026-07-18

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-18, 02:02 PDT
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 5             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK — recovered from OAuth regression |
| **Total**  | **56**        | 3 of 4 sources succeeded |

The reported total of **56 new items** equals pinboard (5) + papers (1) + email (50). The `github` source contributed 0 items because its fetch failed.

Database write verified: `~/dev/knowledge-intake/intake.db` (repo root) modification time is `2026-07-18 02:02:15 PDT`, matching the run time.

## Source-level error: github

The `github` source failed with the recurring masked-401 adapter bug:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known error-handling bug present since 2026-07-04. The GitHub token is expired, so the API returns an HTTP 401 status object instead of an array of starred repos. The adapter never checks `response.ok` (or the array-ness of the payload) before calling `stars.map(...)`, so the auth failure surfaces as a `TypeError` instead of a clear "401 Unauthorized" message.

**Remediation**:

1. Rotate/regenerate the GitHub token used by the ingestion (`GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`) and confirm it has the `read:user` scope needed for the starred-repos endpoint.
2. Fix the adapter to validate the HTTP status before parsing: check `response.ok` (or `Array.isArray(stars)`) and raise a descriptive auth error. This bug has now masked token expiry across every run since 2026-07-04.

## Email source recovered

The `email` source fetched 50 items this run. On the 2026-07-16 and 2026-07-17 runs it failed with `oauth2: "invalid_grant" "Token has been expired or revoked."` (same failure first seen 2026-06-28). The Gmail OAuth token has evidently been re-issued since the 2026-07-17 run, and the `gog` Gmail search path is working again. No action needed; worth watching whether the 50-item batch reflects the backlog accumulated during the two-day outage.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-06-28 | 0        | 0      | 100    | 0     | 100   | email failed: Gmail OAuth `invalid_grant` |
| 2026-07-17 | 1        | 0      | 0      | 0     | 1     | github masked 401; email `invalid_grant` |
| 2026-07-18 | 5        | 1      | 0      | 50    | 56    | github masked 401; email recovered |

Pattern: credentials rotate through failure across sources. GitHub has been down since 2026-07-04 (token expiry masked as a `TypeError`); email was down 2026-07-16 through 2026-07-17 and recovered today. Pinboard and papers have been consistently stable, just low-volume. GitHub is now the only failing source, and it needs both a token rotation and the adapter validation fix to stop masking the real error.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 5 new items
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
[email] fetched 50 new items

Ingestion complete: 56 new items

EXIT_CODE=0
```
