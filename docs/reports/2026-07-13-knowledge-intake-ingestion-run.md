# Knowledge Intake Ingestion Run — 2026-07-13

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-13 (~02:02 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 6             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 30            | OK |
| **Total**  | **37**        | 3 of 4 sources succeeded |

The reported total of **37 new items** equals pinboard (6) + papers (1) + email (30). The `github` source contributed 0 items because it failed before mapping results.

Corroboration: `~/dev/knowledge-intake/intake.db` was modified at 02:02:21 PDT on 2026-07-13, matching the run window. (Note: the database lives at the repo root as `intake.db`, not under `data/` — earlier references to a `data/` directory point at a nonexistent path.)

## Source-level error: github

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known 401-masking bug in the GitHub adapter (recurring since at least the 2026-07-04 run). The adapter calls the GitHub starred-repos API without validating the HTTP status; when the token is expired, the API returns a 401 JSON error object instead of an array, and the subsequent `stars.map(...)` throws a `TypeError` that hides the real authentication failure.

**Remediation** (upstream, in the `knowledge-intake` repo — out of scope for this report):

1. Validate `response.ok` / HTTP status in the GitHub adapter before parsing, and surface a clear auth error on 401.
2. Refresh the GitHub token used by the ingestion (`GITHUB_TOKEN` in `.env` or equivalent) so the source fetches again.

## Source reliability trend

Email and GitHub have alternated as the failing source across recent runs:

| Run date   | pinboard | papers | github | email |
|------------|---------:|-------:|-------:|------:|
| 2026-06-28 | 0        | 0      | 100    | 0 (OAuth expired) |
| 2026-07-12 | 2        | 0      | 0 (401 masked) | 15 |
| 2026-07-13 | 6        | 1      | 0 (401 masked) | 30 |

The Gmail OAuth token recovered after the 2026-06-28 failure and has held since; the GitHub token remains expired and every run since 2026-07-04 has hit the masked-401 path.

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
[email] fetched 30 new items

Ingestion complete: 37 new items

EXIT_CODE=0
```
