# Knowledge Intake Ingestion Run — 2026-07-19

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-19, 02:01 PDT
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 6             | OK |
| papers     | 0             | OK — nothing new |
| github     | 0             | Error — see below |
| email      | 20            | OK |
| **Total**  | **26**        | 3 of 4 sources succeeded |

The reported total of **26 new items** equals pinboard (6) + papers (0) + email (20). The `github` source contributed 0 items because its fetch failed.

Database write verified: `~/dev/knowledge-intake/intake.db` (repo root) modification time is `2026-07-19 02:01:56 PDT`, matching the run time.

## Source-level error: github

The `github` source failed with the recurring masked-401 adapter bug:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known error-handling bug present since 2026-07-04. The GitHub token is expired, so the API returns an HTTP 401 status object instead of an array of starred repos. The adapter never checks `response.ok` (or the array-ness of the payload) before calling `stars.map(...)`, so the auth failure surfaces as a `TypeError` instead of a clear "401 Unauthorized" message.

**Remediation** (unchanged from the 2026-07-18 report — neither step has been done yet):

1. Rotate/regenerate the GitHub token used by the ingestion (`GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`) and confirm it has the `read:user` scope needed for the starred-repos endpoint.
2. Fix the adapter to validate the HTTP status before parsing: check `response.ok` (or `Array.isArray(stars)`) and raise a descriptive auth error. This bug has now masked token expiry for 15 days straight.

## Email source stable

The `email` source fetched 20 items, its second consecutive successful run after recovering from the Gmail OAuth `invalid_grant` outage (2026-07-16 through 2026-07-17). The drop from 50 items on 2026-07-18 to 20 today supports the read that yesterday's batch included the backlog accumulated during the outage; 20 looks like a normal single-day volume.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-06-28 | 0        | 0      | 100    | 0     | 100   | email failed: Gmail OAuth `invalid_grant` |
| 2026-07-17 | 1        | 0      | 0      | 0     | 1     | github masked 401; email `invalid_grant` |
| 2026-07-18 | 5        | 1      | 0      | 50    | 56    | github masked 401; email recovered |
| 2026-07-19 | 6        | 0      | 0      | 20    | 26    | github masked 401; email stable |

Pattern: github remains the only failing source and has been down since 2026-07-04 — token expiry masked as a `TypeError` by the missing-response-validation bug. Email is back to steady state after its two-day OAuth outage. Pinboard is stable and trending slightly up (1 → 5 → 6); papers is stable but near-zero volume. Getting github back requires both the token rotation and the adapter validation fix listed above.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 6 new items
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
[email] fetched 20 new items
Ingestion complete: 26 new items

EXIT_CODE=0
```
