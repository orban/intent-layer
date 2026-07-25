# Knowledge Intake Ingestion Run - 2026-07-25

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-25
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall CLI run completed; two sources errored - see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 0             | OK |
| github     | 0             | Error - failed before a fetched count was available |
| email      | 0             | Error - failed before a fetched count was available |
| **Total**  | **0**         | 2 of 4 sources succeeded |

The reported total of **0 new items** equals pinboard (0) + papers (0). The `github` and `email` sources contributed 0 items because both failed before returning item lists.

## Source-level error: github

The `github` source failed while parsing the GitHub starred repositories response:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => {
...
})', 'stars.map' is undefined)
```

A sanitized follow-up probe against the same endpoint returned HTTP 401 with message `Bad credentials`, so the adapter received an error object instead of the expected array of starred repositories. The fetched count is therefore unavailable for this source, and no GitHub items were added during this run.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-24": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth token has expired or been revoked (`invalid_grant`). The token was read successfully but rejected by Google's token endpoint.

**Remediation**: Re-authenticate `gog` for the configured Gmail account from an interactive terminal, then re-run the ingestion.

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
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-24": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."

Ingestion complete: 0 new items

EXIT_CODE=0
```
