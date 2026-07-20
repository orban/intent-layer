# Knowledge Intake Ingestion Run — 2026-07-20

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-20, 02:01 PDT
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 4             | OK |
| papers     | 0             | OK — nothing new |
| github     | 0             | Error — see below |
| email      | 39            | OK |
| **Total**  | **43**        | 3 of 4 sources succeeded |

The reported total of **43 new items** equals pinboard (4) + papers (0) + email (39). The `github` source contributed 0 items because its fetch failed.

Database write verified: `~/dev/knowledge-intake/intake.db` (repo root) modification time is `2026-07-20 02:01:52 PDT`, matching the run time.

## Source-level error: github

The `github` source failed with the recurring masked-401 adapter bug:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known error-handling bug present since 2026-07-04. The GitHub token is expired, so the API returns an HTTP 401 status object instead of an array of starred repos. The adapter never checks `response.ok` (or the array-ness of the payload) before calling `stars.map(...)`, so the auth failure surfaces as a `TypeError` instead of a clear "401 Unauthorized" message.

**Remediation** (unchanged since the 2026-07-18 report — neither step has been done yet):

1. Rotate/regenerate the GitHub token used by the ingestion (`GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`) and confirm it has the `read:user` scope needed for the starred-repos endpoint.
2. Fix the adapter to validate the HTTP status before parsing: check `response.ok` (or `Array.isArray(stars)`) and raise a descriptive auth error. This bug has now masked token expiry for 16 days straight.

## Email source stable

The `email` source fetched 39 items, its third consecutive successful run since recovering from the Gmail OAuth `invalid_grant` outage (2026-07-16 through 2026-07-17). Volume is up from 20 yesterday but still well under the 50-item post-outage backlog batch on 2026-07-18 — 39 reads as normal day-to-day variance, not a new anomaly.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-06-28 | 0        | 0      | 100    | 0     | 100   | email failed: Gmail OAuth `invalid_grant` |
| 2026-07-17 | 1        | 0      | 0      | 0     | 1     | github masked 401; email `invalid_grant` |
| 2026-07-18 | 5        | 1      | 0      | 50    | 56    | github masked 401; email recovered (backlog) |
| 2026-07-19 | 6        | 0      | 0      | 20    | 26    | github masked 401; email stable |
| 2026-07-20 | 4        | 0      | 0      | 39    | 43    | github masked 401; email stable |

Pattern: github remains the only failing source and has been down since 2026-07-04 — token expiry masked as a `TypeError` by the missing-response-validation bug. Email has settled into a healthy 20–39 items/day range after its two-day OAuth outage. Pinboard is steady at low single digits; papers is stable but near-zero volume. Getting github back requires both the token rotation and the adapter validation fix listed above.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 4 new items
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
[email] fetched 39 new items
Ingestion complete: 43 new items

EXIT_CODE=0
```
