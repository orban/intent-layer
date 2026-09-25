# Knowledge Intake Ingestion Run — 2026-08-13

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-13 (~02:02 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 9             | OK |
| papers     | 0             | Error — `marker_single` not in `$PATH` (new) |
| github     | 0             | Error — recurring masked 401 |
| email      | 50            | OK (page cap hit — backlog remains) |
| **Total**  | **59**        | 2 of 4 sources succeeded |

The reported total of **59 new items** equals pinboard (9) + email (50). The `papers` and `github` sources contributed 0 items because they failed before fetching.

The email source fetched exactly 50 items, which is the per-run page cap — there is more backlog that the next run will continue draining. Gmail OAuth is currently working (it has oscillated between working and `invalid_grant` in past runs; today it authenticated fine).

## Source-level error: papers (new)

```text
[papers] error: Executable not found in $PATH: "marker_single"
```

**Cause**: The papers adapter shells out to `marker_single` (the marker PDF-to-markdown converter) to process new PDFs, and the binary is not on the `PATH` the run sees. This error is new: papers succeeded on 2026-08-09 (0 items) and 2026-08-01 (1 item). Something changed in the environment since — most likely the tool's install location (pipx/uv tool venv, `~/.local/bin`) dropped out of the non-interactive shell's `PATH`, or the tool was removed/reinstalled.

**Remediation**: From an interactive terminal, check `which marker_single`; if missing, reinstall (`pipx install marker-pdf` or the project's documented install), or ensure its bin directory is on the `PATH` exported by `.env` for non-interactive runs.

## Source-level error: github (recurring)

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: Known recurring failure, present in every run since 2026-07-04. The GitHub adapter's token has expired, the API returns an HTTP 401 error object instead of an array of starred repos, and the adapter calls `.map` on it without checking the response status — masking the auth failure as a `TypeError`.

**Remediation**: Regenerate the GitHub token referenced by `.env` in `~/dev/knowledge-intake`. (A proper fix in the adapter — checking `response.ok` before parsing — would surface the real 401, but per nightshift policy the knowledge-intake code isn't modified from these runs.)

## Corroboration

The database write is corroborated by the mtime of `~/dev/knowledge-intake/intake.db` (repo root):

```text
Aug 13 02:02:07 2026 /Users/ryo/dev/knowledge-intake/intake.db
```

checked at `Thu Aug 13 02:02:14 PDT 2026`, seconds after the run completed.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 9 new items
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
[email] fetched 50 new items
Ingestion complete: 59 new items

EXIT_CODE=0
```
