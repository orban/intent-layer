# Knowledge Intake Ingestion Run — 2026-08-08

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-08 (02:01 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **DB write verified**: `~/dev/knowledge-intake/intake.db` mtime `Aug 8 02:01:55 2026`, seconds after the run finished

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 2             | OK |
| github     | 0             | Error — see below |
| email      | 39            | OK |
| **Total**  | **42**        | 3 of 4 sources succeeded |

The reported total of **42 new items** equals pinboard (1) + papers (2) + email (39). The `github` source contributed 0 items because it failed before producing any.

## Source-level error: github

The `github` source failed with the recurring masked-auth-failure bug:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub adapter fetches starred repos and calls `.map()` on the response without checking the HTTP status. When the API returns a non-array body — a 401 error object from an expired/invalid `GITHUB_TOKEN` — the code throws `TypeError: stars.map is not a function`, masking the real auth failure. This same failure was documented in earlier runs; it is an upstream bug in `knowledge-intake`, not fixed here.

Note the auth flip-flop versus the previous run (2026-06-28): back then github succeeded (100 items) while Gmail failed with `invalid_grant`. This run, github's token is rejected while Gmail works again.

**Remediation**:

1. Refresh the `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env` (check expiry at github.com → Settings → Developer settings → Personal access tokens).
2. Upstream fix (out of scope for this report): in the github adapter, check `response.ok` / `Array.isArray(stars)` before mapping, and surface the HTTP status in the error message.

## Email source note

Gmail OAuth is back in its working state this run (it has oscillated between working and `invalid_grant` across runs). It fetched 39 items — under the `maxResults=50` page cap — so the newsletter backlog since the last successful email fetch appears fully drained rather than truncated.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
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
[email] fetched 39 new items

Ingestion complete: 42 new items

EXIT_CODE=0
```
