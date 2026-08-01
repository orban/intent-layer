# Knowledge Intake Ingestion Run — 2026-08-01

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-01 (completed 02:01 local)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Verification**: `~/dev/knowledge-intake/intake.db` mtime updated to Aug 1 02:01:48 (size 159,002,624 bytes), confirming the run wrote data.

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 0             | OK |
| papers     | 1             | OK |
| github     | 0             | Error — see below |
| email      | 40            | OK |
| **Total**  | **41**        | 3 of 4 sources succeeded |

The reported total of **41 new items** equals pinboard (0) + papers (1) + email (40). The `github` source contributed 0 items because it failed before producing any.

Email fetched 40 items — below the `maxResults=50` page cap, so the newsletter backlog that built up during the July `invalid_grant` outages is now fully drained (the 2026-07-28 run hit the cap at exactly 50). Gmail OAuth was healthy this run: no `invalid_grant` error and no Keychain timeout.

## Source-level error: github (recurring since 2026-07-04)

```text
[github] error: stars.map is not a function (TypeError — stars.map is undefined)
```

**Cause**: The GitHub adapter calls `stars.map(...)` on the parsed response of the starred-repos API without checking the HTTP status. When the request fails auth (HTTP 401 from an expired or revoked `GITHUB_TOKEN`), the response body is an error object, not an array, so the real 401 is masked as a `TypeError`. This has recurred on every run since 2026-07-04 (also seen 07-26, 07-27, 07-28).

**Remediation** (documented, intentionally not fixed in this operational run):

1. Rotate or refresh the `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env` (needs the starred-repos read scope).
2. Fix the adapter to check `response.ok` (and `Array.isArray(stars)`) before mapping, so auth failures surface as HTTP errors instead of a `TypeError`.

## Comparison with prior runs

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-07-26 | 1        | error  | error  | error | 1     |
| 2026-07-27 | 2        | 4      | error  | error | 6     |
| 2026-07-28 | 1        | 0      | error  | 50*   | 51    |
| **2026-08-01** | **0** | **1**  | **error** | **40** | **41** |

\* 50 = `maxResults` page cap; backlog remained after that run. The 40 fetched this run clears it.

github has now failed 4 consecutive logged runs with the same masked-401 error. papers recovered from the 07-26 `EINTR` scandir error and has been stable since.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 0 new items
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
Ingestion complete: 41 new items

EXIT_CODE=0
```
