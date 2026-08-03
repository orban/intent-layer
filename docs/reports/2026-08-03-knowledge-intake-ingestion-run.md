# Knowledge Intake Ingestion Run — 2026-08-03

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-03 (~02:02 local)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Database**: `~/dev/knowledge-intake/intake.db` mtime updated to 2026-08-03 02:02, confirming the run persisted data

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 39            | OK |
| **Total**  | **39**        | 3 of 4 sources succeeded |

The reported total of **39 new items** equals pinboard (0) + papers (0) + email (39). The `github` source contributed 0 items because it failed before producing any.

## Comparison to recent runs

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-07-28 | 1        | 0      | error  | 50    | 51 |
| 2026-08-01 | 0        | 1      | error  | 40    | 41 |
| 2026-08-02 | 3        | 0      | error  | 21    | 24 |
| 2026-08-03 | 0        | 0      | error  | 39    | 39 |

Email fetched 39 items — below the 50-per-page cap, so no backlog remains beyond this run. Gmail OAuth, which has oscillated between `invalid_grant` failures and recovery in past runs (it failed outright on 2026-06-28), is currently working and has been stable across the last several runs.

## Source-level error: github

The `github` source failed with the same error as every run since 2026-07-04:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub adapter fetches starred repos and calls `.map()` on the response body without checking the HTTP status. When the request fails (a 401 from an expired or insufficiently-scoped token), the API returns an error object instead of an array, and the `TypeError` masks the underlying auth failure. This is the recurring 401-masking bug documented in prior run reports.

**Remediation** (unchanged, upstream fix in `knowledge-intake` needed):

1. Refresh the GitHub token in `~/dev/knowledge-intake/.env` (needs the `read:user` scope for the starred endpoint).
2. Fix the adapter to check `response.ok` / `Array.isArray(stars)` before mapping, so auth failures surface as auth errors rather than a `TypeError`.

This is a known issue in the ingestion pipeline plus a stale credential on the run host; it is out of scope for this operational run.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
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

Ingestion complete: 39 new items

EXIT_CODE=0
```
