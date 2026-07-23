# Knowledge Intake Ingestion Run — 2026-07-23

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-23 (02:02 PDT / 09:02 UTC)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Database**: `~/dev/knowledge-intake/intake.db` modified at 2026-07-23 02:02:19 local, confirming the run wrote data

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK |
| **Total**  | **52**        | 3 of 4 sources succeeded |

The reported total of **52 new items** equals pinboard (1) + papers (1) + email (50). The `github` source contributed 0 items because its adapter threw before producing any.

## Source-level error: github

The `github` source failed with the same runtime TypeError as every run since 2026-07-04:

```text
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
```

**Cause**: This is the known masked-401 bug. The GitHub token expired on **2026-07-04** — **19 days ago** as of this run. The adapter fetches the starred-repos endpoint without checking `response.ok`, so GitHub's 401 error body (a JSON object, not an array) flows into `stars.map(...)` and surfaces as a confusing `stars.map is not a function` TypeError instead of a clear authentication error.

**Remediation** (both still outstanding since 2026-07-04):

1. Rotate the GitHub token referenced in `~/dev/knowledge-intake/.env` and re-run the ingestion.
2. Fix the adapter to validate `response.ok` (and content type) before calling `.map()`, so auth failures report as HTTP 401 rather than a TypeError.

## Source status: email

The `email` source is healthy: 50 items fetched, again the Gmail search per-page maximum (`maxResults=50`), so the source is still paging through a backlog rather than reflecting one day's volume. The recovery from the Gmail OAuth `invalid_grant` failure documented in the 2026-06-28 report continues to hold.

## Source status: papers

The `papers` source returned 1 item — its first non-zero fetch since 2026-05-23. Nothing was wrong with the source in the intervening runs; it simply had no new items to pick up. Worth a glance next run to confirm it keeps tracking new material.

## Cross-run comparison

| Run date   | pinboard | papers | github | email | Total | Failing source |
|------------|---------:|-------:|-------:|------:|------:|----------------|
| 2026-05-23 | 20       | 9      | 100    | 0     | 129   | email (Keychain/OAuth) |
| 2026-05-25 | 0        | 0      | 100    | 0     | 100   | email (OAuth) |
| 2026-06-14 | 0        | 0      | 100    | 0     | 100   | email (OAuth) |
| 2026-06-28 | 0        | 0      | 100    | 0     | 100   | email (`invalid_grant`) |
| 2026-07-21 | 5        | 0      | 0      | 50    | 55    | github (masked 401) |
| 2026-07-22 | 2        | 0      | 0      | 50    | 52    | github (masked 401) |
| 2026-07-23 | 1        | 1      | 0      | 50    | 52    | github (masked 401) |

The pattern holds for a third consecutive run: email keeps draining its backlog at exactly 50 items per run, while github has returned 0 items on every run since its token expired on 2026-07-04. Each day the token rotation is deferred, the starred-repos backlog behind it grows — prior runs show github paging at a 100-item cap before the failure, so catch-up will take multiple runs once the token is rotated.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
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

Ingestion complete: 52 new items

EXIT_CODE=0
```
