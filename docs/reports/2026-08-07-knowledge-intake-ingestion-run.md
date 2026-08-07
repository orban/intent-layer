# Knowledge Intake Ingestion Run — 2026-08-07

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-07 (02:02 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Corroboration**: `~/dev/knowledge-intake/intake.db` mtime updated to Aug 7 02:02:01, seconds before the post-run check — the run wrote data.

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 4             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 40            | OK |
| **Total**  | **45**        | 3 of 4 sources succeeded |

The reported total of **45 new items** equals pinboard (4) + papers (1) + email (40). The `github` source contributed 0 items because it failed before producing any.

Email fetched 40 items, below the `maxResults=50` page cap, so the Gmail backlog is fully drained this run. Notably, Gmail OAuth is healthy again — it was in its `invalid_grant` expired state as recently as 2026-08-04. The token state continues to oscillate between runs.

## Source-level error: github

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the recurring GitHub 401 masked as a `TypeError`. The GitHub starred-repos API call fails authentication (401), the adapter does not check the HTTP status, and the error-shaped JSON response body is passed to `stars.map(...)` — which throws because the body is an object, not an array. This failure has occurred on every run since 2026-07-04.

**Remediation** (upstream, in `knowledge-intake` — not fixed here):

1. Refresh the GitHub token in `.env` (`GITHUB_TOKEN` or equivalent) — it has likely expired or been revoked.
2. Fix the adapter to check `response.ok` / HTTP status before parsing, so auth failures surface as `401 Unauthorized` instead of a misleading `TypeError`.

This is a known upstream issue in the `knowledge-intake` repo; per the standing run pattern it is documented rather than fixed from this task.

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
[email] fetched 40 new items

Ingestion complete: 45 new items

EXIT_CODE=0
```
