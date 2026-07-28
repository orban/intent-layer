# Knowledge Intake Ingestion Run — 2026-07-28

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-28 (02:01 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)
- **Verification**: `intake.db` at the repo root had mtime `Jul 28 02:01:59`, seconds before the check — the run wrote data.

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 1             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 50            | OK (recovered — see below) |
| **Total**  | **51**        | 3 of 4 sources succeeded |

The reported total of **51 new items** equals pinboard (1) + papers (0) + email (50). The `github` source contributed 0 items because it failed before producing any.

## Source-level error: github

The `github` source failed with the recurring masked-authentication bug:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub token in `.env` is no longer valid. A direct probe during this run confirmed it:

```bash
curl --silent --output /dev/null --write-out "%{http_code}" \
  --header "Authorization: Bearer $GITHUB_TOKEN" \
  --header "Accept: application/vnd.github.star+json" \
  "https://api.github.com/user/starred?per_page=1"
# → 401
```

GitHub returns a `{"message": "Bad credentials", ...}` error object instead of an array, and the fetcher calls `stars.map` on it without first checking the HTTP status, so the real 401 is masked as a `TypeError`. This is the same failure seen in the 2026-07-26 and 2026-07-27 runs.

**Remediation**:

1. Rotate the expired/revoked GitHub token and update `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`.
2. (Code fix, out of scope for this run) Check `response.ok` in the github fetcher before parsing, so auth failures surface as HTTP errors rather than `TypeError`.

## Recovery: email

The `email` source fetched **50 items** after failing with `oauth2: "invalid_grant" "Token has been expired or revoked."` in every logged run from 2026-06-28 through 2026-07-27. The `gog` Gmail OAuth token has evidently been re-minted since last night's run.

Note the Gmail query uses `maxResults=50`, and this run returned exactly 50 items while draining roughly a month of backlog — the fetch was likely page-capped. Expect the next run to pick up additional backlog items rather than dropping back to a small steady-state count immediately.

## Comparison with prior runs

| Run date   | pinboard | papers | github | email | Total | Notes |
|------------|---------:|-------:|-------:|------:|------:|-------|
| 2026-06-28 | 0        | 0      | 100    | 0     | 100   | email failing (`invalid_grant`) |
| 2026-07-26 | 1        | error  | error  | 0     | 1     | papers hit transient `EINTR` scandir error |
| 2026-07-27 | 2        | 4      | error  | 0     | 6     | github + email both failing |
| **2026-07-28** | **1** | **0** | **error** | **50** | **51** | email recovered; github still down |

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 1 new items
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
[email] fetched 50 new items

Ingestion complete: 51 new items

EXIT_CODE=0
```
