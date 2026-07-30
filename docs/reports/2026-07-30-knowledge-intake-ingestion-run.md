# Knowledge Intake Ingestion Run — 2026-07-30

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-30 (~02:02 local)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 5             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 43            | OK |
| **Total**  | **49**        | 3 of 4 sources succeeded |

The reported total of **49 new items** equals pinboard (5) + papers (1) + email (43). The `github` source contributed 0 items because it failed before producing any.

Corroboration: `~/dev/knowledge-intake/intake.db` (repo root) mtime is `Jul 30 02:02:04 2026`, matching the run. Cumulative DB counts after this run: pinboard 4,837 · papers 774 · email 1,109 · github 134 · **total 6,854**.

## Source-level error: github

The `github` source failed with:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the recurring adapter bug first seen on 2026-07-04. The GitHub starred-repos request returns HTTP 401 (expired/invalid token), the adapter does not check the response status, and the JSON error body (an object, not an array) reaches `stars.map`, surfacing as a `TypeError` that masks the real auth failure.

**Remediation**:

1. Refresh the `GITHUB_TOKEN` (or equivalent) in `~/dev/knowledge-intake/.env`.
2. Upstream fix (not applied here — knowledge-intake repo, out of scope for this run): check `response.ok`/status before parsing, and fail with the HTTP status so 401s are not masked as `TypeError`.

## Notes on email

The Gmail OAuth token worked this run. It has oscillated between working and `invalid_grant` across runs (failed 2026-06-28, worked 2026-07-26 through today), so treat it as fragile. The fetch cap is `maxResults=50`; the 2026-07-28 run returned exactly 50 (capped, backlog remaining), while today's 43 is under the cap, so the newsletter backlog is drained.

## Comparison with recent runs

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-06-28 | 0        | 0      | 100    | 0 (OAuth error) | 100 |
| 2026-07-28 | 1        | 0      | 0 (error) | 50 (capped) | 51 |
| 2026-07-30 | 5        | 1      | 0 (error) | 43    | 49 |

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
[email] fetched 43 new items

Ingestion complete: 49 new items

EXIT_CODE=0
```
