# Knowledge Intake Ingestion Run — 2026-08-09

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-09
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Corroboration**: `intake.db` at the repo root was modified at 02:01:36 on 2026-08-09 (162,275,328 bytes), consistent with this run writing to it.

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 2             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 18            | OK |
| **Total**  | **20**        | 3 of 4 sources succeeded |

The reported total of **20 new items** equals pinboard (2) + papers (0) + email (18). The `github` source contributed 0 items because it failed before producing any.

## Source-level error: github

The `github` source failed with a TypeError:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the recurring 401-masking bug in the github adapter. When the GitHub token is expired or invalid, the API returns an HTTP 401 error object instead of an array of starred repos. The adapter calls `stars.map(...)` on that error object without first checking the response status, so the auth failure surfaces as a misleading `TypeError` rather than a clear "token expired" message.

**Remediation**:

1. Refresh the GitHub token referenced in `~/dev/knowledge-intake/.env` (mint a new personal access token with the scopes needed to read starred repos).
2. Longer term, fix the adapter to check the HTTP status (or `Array.isArray(stars)`) before mapping, so an auth failure reports itself as one.

This is a known recurring issue documented in prior run reports; it is an auth/environment problem masked by a missing response-shape check, not a new pipeline defect.

## Email source recovered

The `email` source, which failed on 2026-06-28 with an OAuth `invalid_grant` error, succeeded this run and fetched 18 items. The count is below the 50-item page cap, so there is no truncated backlog — the Gmail OAuth token is currently valid and the source is fully caught up.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 2 new items
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
[email] fetched 18 new items

Ingestion complete: 20 new items

EXIT_CODE=0
```
