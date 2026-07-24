# Knowledge Intake Ingestion Run — 2026-07-24

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-24 (~02:02 PDT / 09:02 UTC)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **DB verification**: `~/dev/knowledge-intake/intake.db` mtime `Jul 24 02:02:00 2026` (local), matching the run window

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 4             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK (Gmail pagination cap) |
| **Total**  | **55**        | 3 of 4 sources succeeded |

The reported total of **55 new items** equals pinboard (4) + papers (1) + email (50). The `github` source contributed 0 items because it failed before producing any.

## Source-level error: github

The `github` source failed with the same masked authentication error seen on every run since 2026-07-04:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub API token expired on 2026-07-04 (20 days before this run). The adapter calls the starred-repos endpoint without checking `response.ok`; on a 401 the response body is an error object (`{"message": "Bad credentials", ...}`) rather than an array, so the subsequent `stars.map(...)` throws a `TypeError` that masks the real 401.

**Remediation**:

1. Rotate the GitHub token referenced in `~/dev/knowledge-intake/.env` (mint a new PAT with the `read:user` scope for starred repos).
2. Fix the adapter to check `response.ok` (or `Array.isArray(stars)`) before mapping, and surface the HTTP status in the error message so auth failures are not reported as type errors.

The upstream `knowledge-intake` repo is out of scope for this run; this report documents the failure without patching it.

## Note: email at pagination cap

The `email` source fetched exactly **50** items, which is the Gmail API `maxResults=50` page size used by the adapter. Fetching exactly the cap means the newsletter backlog is likely not fully drained — the source has hit this cap repeatedly since recovering from its OAuth outage, draining incrementally at 50 items per run.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-06-28 | 0        | 0      | 100    | 0     | 100   | email OAuth `invalid_grant` |
| 2026-07-12 | —        | —      | 0      | —     | 17    | github token expired 07-04 |
| 2026-07-13 | —        | —      | 0      | —     | 37    | |
| 2026-07-14 | —        | —      | 0      | —     | 35    | |
| 2026-07-15 | —        | —      | 0      | —     | 45    | |
| 2026-07-16 | —        | —      | 0      | —     | 7     | email OAuth regression |
| 2026-07-17 | —        | —      | 0      | —     | 56    | |
| 2026-07-23 | 1        | 1      | 0      | 50    | 52    | papers recovered from dormancy; email at cap |
| **2026-07-24** | **4** | **1** | **0** | **50** | **55** | this run |

Per-source breakdowns for 07-12 through 07-17 are not reproduced here (those reports live on their own stacked branches); totals are carried forward from the run-report series. The pattern holds: github has been dark for 20 days on the expired token, email continues to drain its backlog at the 50-item pagination cap, and pinboard/papers contribute small steady volumes.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 4 new items
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
Ingestion complete: 55 new items

EXIT_CODE=0
```
