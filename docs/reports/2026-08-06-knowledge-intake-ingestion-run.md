# Knowledge Intake Ingestion Run — 2026-08-06

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-06
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **DB write verified**: `intake.db` mtime `Aug 6 02:01:58 2026`, seconds after the run finished

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 7             | OK |
| papers     | 2             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK (hit page cap — see note) |
| **Total**  | **59**        | 3 of 4 sources succeeded |

The reported total of **59 new items** equals pinboard (7) + papers (2) + email (50). The `github` source contributed 0 items because it failed before mapping results.

**Email page-cap note**: email returned exactly 50 items, which is the `maxResults=50` Gmail page cap. This almost certainly means a backlog remains from the OAuth outage on prior runs; the next run should pick up another page.

## Source-level error: github

The `github` source failed with the same error seen on every run since 2026-07-04:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub token has expired, so the starred-repos API call returns an HTTP 401 error object instead of an array. The adapter does not check the response status before calling `.map()`, so the auth failure is masked as a `TypeError`. This is the recurring upstream bug in the github adapter, not a new failure mode.

**Remediation**:

1. Mint a fresh GitHub personal access token and update it in `~/dev/knowledge-intake/.env`.
2. Fix the adapter to check `Array.isArray(stars)` (or the HTTP status) and surface the real 401 error instead of the masked `TypeError`.

## Gmail OAuth state

Gmail OAuth is currently **working**. The `email` source fetched 50 items with no `invalid_grant` error. This auth has oscillated across runs (failed 2026-06-28 with `invalid_grant`, worked 2026-08-03, working today), so treat it as fragile.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 7 new items
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
Ingestion complete: 59 new items

EXIT_CODE=0
```
