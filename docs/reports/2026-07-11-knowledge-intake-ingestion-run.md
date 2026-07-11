# Knowledge Intake Ingestion Run — 2026-07-11

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-11
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 18            | OK |
| papers     | 2             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK |
| **Total**  | **70**        | 3 of 4 sources succeeded |

The reported total of **70 new items** equals pinboard (18) + papers (2) + email (50). The `github` source contributed 0 items because it failed before mapping results.

## Source-level error: github

The `github` source failed with a TypeError while mapping the starred-repos response:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the known error-handling gap in the GitHub adapter — it calls `.map()` on the response body without checking the HTTP status first. When the GitHub API returns a 401 (expired or revoked personal access token), the body is an error object rather than an array, so the failure surfaces as a misleading `stars.map is not a function` TypeError instead of an authentication error. The same masked 401 appeared in the 2026-07-04 through 2026-07-07 runs.

**Remediation**:

1. Refresh the GitHub personal access token used by the adapter (regenerate at github.com/settings/tokens and update `.env` in `~/dev/knowledge-intake`).
2. Fix the adapter to check `response.ok` / HTTP status before mapping, so auth failures report as 401 errors rather than TypeErrors.

Notably, the `email` source recovered this run (50 items) after failing with `invalid_grant` on 2026-06-28 — the Gmail OAuth token has been refreshed. The credential failures continue to alternate between github and email across runs.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 18 new items
[papers] fetched 2 new items
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
Ingestion complete: 70 new items
EXIT_CODE=0
```
