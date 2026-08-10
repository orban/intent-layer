# Knowledge Intake Ingestion Run — 2026-08-10

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-10
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 8             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 23            | OK |
| **Total**  | **31**        | 3 of 4 sources succeeded |

The reported total of **31 new items** equals pinboard (8) + papers (0) + email (23). The `github` source contributed 0 items because it failed before producing any.

Email fetched 23 items, under the 50-item page cap (`maxResults=50`), so there is no remaining backlog — the Gmail OAuth token that recovered by 2026-08-07 is still valid.

## Source-level error: github

The `github` source failed with the same masked error seen on every run since 2026-07-04:

```text
[github] error: stars.map is not a function. ('stars.map' is undefined)
```

**Cause**: The GitHub adapter does not check the HTTP status of the starred-repos response. The token in `.env` is expired, GitHub returns 401 with a JSON error object instead of an array, and the adapter crashes calling `.map()` on it. Confirmed directly on 2026-07-28 by probing `/user/starred` with the `.env` token (HTTP 401).

**Remediation**:

1. Mint a fresh GitHub personal access token and update the token in `~/dev/knowledge-intake/.env`.
2. Upstream fix (out of scope for this run): the adapter should check `response.ok` / `Array.isArray(stars)` before mapping, so auth failures surface as auth errors rather than a `TypeError`.

This is a known recurring auth issue plus an upstream error-handling bug in `knowledge-intake`; the other three sources fetched normally.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 8 new items
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
[email] fetched 23 new items
Ingestion complete: 31 new items
EXIT_CODE=0
```
