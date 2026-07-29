# Knowledge Intake Ingestion Run — 2026-07-29

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-29
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Database**: `~/dev/knowledge-intake/intake.db` mtime confirmed updated at run completion (02:01:47 PDT)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 2             | OK |
| papers     | 2             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK (page cap hit — see note) |
| **Total**  | **54**        | 3 of 4 sources succeeded |

The reported total of **54 new items** equals pinboard (2) + papers (2) + email (50). The `github` source contributed 0 items because it failed before producing any.

**Email page cap**: email returned exactly 50 items, which is the `maxResults=50` page limit on the Gmail query. That means the fetch was truncated at one page and a backlog likely remains; subsequent runs will continue draining it.

**Gmail OAuth state**: working this run. The OAuth token that failed with `invalid_grant` on 2026-06-28 has since been refreshed and continues to hold — email fetched successfully today.

## Source-level error: github

The `github` source failed with the same error seen in every run since 2026-07-04:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This `TypeError` masks an upstream HTTP 401 from the GitHub starred-repos API. The adapter fetches `/user/starred` and assumes the response body is an array; when authentication fails, GitHub returns a JSON error object (`{"message": "Bad credentials", ...}`) instead, so `stars.map` is undefined. The real problem is an expired or revoked GitHub token in the environment, not the mapping code.

**Remediation**:

1. Rotate the GitHub token referenced in `~/dev/knowledge-intake/.env` (a token with the starring read scope) and re-run.
2. Separately, the adapter should check `Array.isArray(stars)` (or the HTTP status) before mapping, so auth failures surface as a clear 401 instead of a misleading `TypeError`. This is a known pipeline defect; fixing it is out of scope for this operational run.

This failure is recurring and pre-existing — it does not indicate a new regression in this run.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 2 new items
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

Ingestion complete: 54 new items

EXIT_CODE=0
```
