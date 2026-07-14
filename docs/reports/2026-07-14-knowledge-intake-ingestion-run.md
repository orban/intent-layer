# Knowledge Intake Ingestion Run — 2026-07-14

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-14 (02:02 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; one source errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 5             | OK |
| papers     | 0             | OK |
| github     | 0             | Error — see below |
| email      | 30            | OK |
| **Total**  | **35**        | 3 of 4 sources succeeded |

The reported total of **35 new items** equals pinboard (5) + papers (0) + email (30). The `github` source contributed 0 items because it failed before mapping results.

Corroboration: `~/dev/knowledge-intake/intake.db` (repo root) mtime updated to 2026-07-14 02:02, matching the run.

## Source-level error: github

The `github` source failed with `TypeError: stars.map is not a function` while mapping starred repos:

```text
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
```

**Cause**: This is the known error-masking bug in the GitHub adapter, failing every run since 2026-07-04. When the GitHub API returns HTTP 401 (expired/invalid token), the adapter doesn't check the response status; the error-body JSON isn't an array, so the subsequent `stars.map(...)` call throws `TypeError`, masking the real authentication failure.

**Remediation**:

1. Refresh the GitHub token in `~/dev/knowledge-intake/.env` (regenerate a PAT with permission to read starred repos).
2. Upstream fix (out of scope for this run): check the HTTP response status before parsing, and surface the status code in the error message instead of letting `stars.map` throw.

This is an environment/auth issue on the run host plus a pre-existing adapter error-handling defect in `knowledge-intake`, not a regression from this run. The other three sources fetched normally.

## Source health notes

- **email**: Healthy — 30 items. Gmail OAuth recovered on its own by 2026-07-12 (after the 2026-06-28 `invalid_grant` failure) and has held since.
- **pinboard**: Healthy — 5 items (6 on 2026-07-13).
- **papers**: 0 items, no error — no new papers since the last run.
- **github**: Failing every run since 2026-07-04 with the masked-401 pattern above. Credential health has alternated across runs: on 2026-06-28 github fetched 100 items while email failed; since 2026-07-04 the pattern is reversed.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 5 new items
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
[email] fetched 30 new items
Ingestion complete: 35 new items

EXIT_CODE=0
```
