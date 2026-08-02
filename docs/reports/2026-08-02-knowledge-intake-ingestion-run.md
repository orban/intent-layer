# Knowledge Intake Ingestion Run — 2026-08-02

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-02 (02:02 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 3             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 21            | OK |
| **Total**  | **24**        | 3 of 4 sources succeeded |

The reported total of **24 new items** equals pinboard (3) + papers (0) + email (21). The `github` source contributed 0 items because it failed before producing any.

Post-run verification: `intake.db` at the repo root had mtime `Aug 2 02:02:05 2026`, seconds before the check — the run wrote to the database.

## Source-level error: github

The `github` source failed with the recurring error seen in every logged run since 2026-07-04:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub starred-repos API call returns a non-array response (almost certainly a 401/403 error object from an expired or invalid `GITHUB_TOKEN`), and the adapter calls `.map()` on it without checking the response status. The real auth failure is masked as a `TypeError`.

**Remediation**: Refresh the `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`, and ideally patch the github adapter to check `response.ok` before parsing so auth failures surface as such. This is a known upstream bug; documented here, not fixed in this run.

## Gmail status: healthy, backlog cleared

The `email` source fetched 21 items — well under the `maxResults=50` page cap. Recent history:

- 2026-07-28: 50 items (cap hit, backlog remained)
- 2026-08-01: 40 items (under cap)
- 2026-08-02: 21 items (under cap — steady-state nightly volume)

The Gmail OAuth token is currently valid and the newsletter backlog is fully drained.

## Comparison to prior runs

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-07-26 | 1        | —      | error  | —     | 1 |
| 2026-07-27 | 2        | 4      | error  | error | 6 |
| 2026-07-28 | 1        | 0      | error  | 50    | 51 |
| 2026-08-01 | 0        | 1      | error  | 40    | 41 |
| **2026-08-02** | **3**    | **0**  | **error** | **21** | **24** |

The github adapter has now failed on five consecutive logged runs with the identical masked-401 error.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 3 new items
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
[email] fetched 21 new items
Ingestion complete: 24 new items

EXIT_CODE=0
```
