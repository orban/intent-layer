# Knowledge Intake Ingestion Run — 2026-08-17

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-08-17 (~02:01 PDT)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Branch**: `nightshift/knowledge-ingest-report-2026-08-17` (stacked on `nightshift/knowledge-ingest-report-2026-06-28`)
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 15            | OK |
| papers     | 0             | Error — `marker_single` not in `$PATH` (recurring since 08-13) |
| github     | 0             | Error — recurring masked 401 |
| email      | 50            | OK (page cap hit — backlog remains) |
| **Total**  | **65**        | 2 of 4 sources succeeded |

The reported total of **65 new items** equals pinboard (15) + email (50). The `papers` and `github` sources contributed 0 items because they failed before fetching.

The email source again fetched exactly 50 items, the per-run page cap, so the newsletter backlog is still draining — this is the second consecutive run at the cap (08-13 also returned 50). Gmail OAuth authenticated fine this run; it has oscillated between working and `invalid_grant` in the past (see the 06-28 report).

## Comparison to prior runs

| Run   | pinboard | papers | github | email | Total |
|-------|---------:|-------:|-------:|------:|------:|
| 08-10 | —        | —      | —      | —     | 31 |
| 08-13 | 9        | err    | err    | 50    | 59 |
| 08-17 | 15       | err    | err    | 50    | 65 |

Same failure profile as 08-13; only the pinboard count moved (9 → 15 over four days).

## Source-level error: papers (recurring)

```text
[papers] error: Executable not found in $PATH: "marker_single"
```

**Cause**: The papers adapter shells out to `marker_single` (marker-pdf) and the binary is not on the `PATH` seen by the non-interactive run. First seen 08-13; unchanged since. Most likely the tool's bin directory (pipx/uv tool venv, `~/.local/bin`) is missing from the `PATH` that `.env` exports, or the tool was removed.

**Remediation**: From an interactive terminal, `which marker_single`; if missing, reinstall (`pipx install marker-pdf` or the project's documented install), or add its bin directory to the `PATH` exported by `.env`.

## Source-level error: github (recurring)

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: Known recurring failure, present in every run since 2026-07-04. The GitHub token has expired, the API returns an HTTP 401 error object instead of an array, and the adapter calls `.map` on it without checking the response status — masking the auth failure as a `TypeError`.

**Remediation**: Regenerate the GitHub token referenced by `.env` in `~/dev/knowledge-intake`. (Checking `response.ok` in the adapter would surface the real 401, but per nightshift policy the knowledge-intake code isn't modified from these runs.)

## Corroboration

The database write is corroborated by the mtime of `~/dev/knowledge-intake/intake.db` (repo root):

```text
Aug 17 02:01:55 2026 /Users/ryo/dev/knowledge-intake/intake.db
```

checked at `Mon Aug 17 02:01:59 PDT 2026`, seconds after the run completed.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 15 new items
[papers] error: Executable not found in $PATH: "marker_single"
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => {
      ...
    })', 'stars.map' is undefined)
[email] fetched 50 new items
Ingestion complete: 65 new items

EXIT_CODE=0
```
