# Knowledge Intake Ingestion Run — 2026-08-18

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-18 (~02:01 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)
- **Corroboration**: `~/dev/knowledge-intake/intake.db` mtime `Aug 18 02:01:55 2026`, size 164,630,528 bytes — written by this run.

## Per-source results

| Source     | Items fetched | Status | Notes |
|------------|--------------:|--------|-------|
| pinboard   | 3             | OK | |
| papers     | 0             | Error | `marker_single` not on `$PATH` (recurring since 2026-08-13) |
| github     | 0             | Error | HTTP 401 masked as `stars.map is not a function` (recurring since 2026-07-04) |
| email      | 8             | OK | Under the 50-item page cap — no backlog remaining |
| **Total**  | **11**        | 2 of 4 sources succeeded | |

Arithmetic check: pinboard (3) + papers (0) + github (0) + email (8) = **11**, matching the CLI's `Ingestion complete: 11 new items`.

## Source-level errors

### papers — `marker_single` missing from PATH

```text
[papers] error: Executable not found in $PATH: "marker_single"
```

**Cause**: The `marker-pdf` binary is not on `$PATH` in the shell the ingestion runs under. First seen 2026-08-13; still present. Environment issue on the run host, not a code defect.

**Remediation**: Reinstall or re-link `marker-pdf` (e.g. `uv tool install marker-pdf` or `pipx install marker-pdf`) so `marker_single` resolves, or set the binary path explicitly in `.env`.

### github — expired token masked as a TypeError

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: The GitHub token in `.env` returns HTTP 401 on `/user/starred`; the adapter doesn't check the response status, so the error JSON object reaches `stars.map` and throws. Same failure every run since 2026-07-04. Upstream bug in `knowledge-intake` (out of scope here) on top of an expired token.

**Remediation**: Rotate `GITHUB_TOKEN` in `~/dev/knowledge-intake/.env`; separately, the adapter should check `res.ok` before parsing.

## Email state

Gmail OAuth is currently healthy — the `invalid_grant` failures last seen 2026-08-04 haven't recurred. 8 items is well under the `maxResults=50` page cap, so the newsletter backlog is drained.

## Comparison to prior runs

| Run | pinboard | papers | github | email | Total |
|-----|---------:|-------:|-------:|------:|------:|
| 2026-08-07 | 4 | 1 | err | 40 | 45 |
| 2026-08-10 | 8 | 0 | err | 23 | 31 |
| 2026-08-13 | 9 | err | err | 50 (capped) | 59 |
| **2026-08-18** | 3 | err | err | 8 | **11** |

Lower total than 08-13 mostly because email caught up (50 capped → 8 uncapped) and pinboard activity was lighter. The two failing sources are unchanged.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 3 new items
[papers] error: Executable not found in $PATH: "marker_single"
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
[email] fetched 8 new items
Ingestion complete: 11 new items

EXIT_CODE=0
```
