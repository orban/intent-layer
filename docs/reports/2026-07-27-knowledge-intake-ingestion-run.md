# Knowledge Intake Ingestion Run — 2026-07-27

Operational run of the `knowledge-intake` ingestion pipeline, capturing how many items each source returned.

## Command

```bash
cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest
```

- **Run date**: 2026-07-27 (~02:02 local)
- **Repo**: `~/dev/knowledge-intake` (sibling to `intent-layer`)
- **Runtime**: `bun`
- **Exit code**: `0` (overall run succeeded; two sources errored — see below)
- **Corroboration**: `~/dev/knowledge-intake/intake.db` mtime updated to Jul 27 02:02:01

## Per-source results

| Source     | Items fetched | Status |
|------------|--------------:|--------|
| pinboard   | 2             | OK |
| papers     | 4             | OK |
| github     | 0             | Error — see below |
| email      | 0             | Error — see below |
| **Total**  | **6**         | 2 of 4 sources succeeded |

The reported total of **6 new items** equals pinboard (2) + papers (4). The `github` and `email` sources contributed 0 items because each failed before fetching.

## Source-level error: github

The `github` source failed with a TypeError before mapping starred repos:

```text
[github] error: stars.map is not a function. (In 'stars.map(({ starred_at, repo }) => { ... })', 'stars.map' is undefined)
```

**Cause**: This is the recurring 401-masked-as-TypeError bug seen on runs since 2026-07-04. The GitHub API call returns a non-array error body (almost certainly a `401 Unauthorized` JSON object from an expired/revoked token), and the adapter passes it straight to `.map()` without checking the response status or shape. The real failure — bad GitHub credentials — is masked by the downstream TypeError. The last successful github fetch was the 2026-06-28 run (100 items).

**Remediation**:

1. Refresh the GitHub token used by the adapter (check `.env` in `~/dev/knowledge-intake` for the token variable) and confirm it has the scope needed for `/user/starred`.
2. Code fix (still outstanding): in the github adapter, check `response.ok` / `Array.isArray(stars)` before mapping, and surface the HTTP status and error body in the thrown error so auth failures are visible directly.

Documented but not fixed here — the adapter lives in the `knowledge-intake` repo, outside this task's scope.

## Source-level error: email

The `email` source failed during a Gmail search via the `gog` CLI:

```text
[email] error: gog gmail search failed (exit 1): Get "https://gmail.googleapis.com/gmail/v1/users/me/messages?alt=json&fields=messages%28id%2CthreadId%29%2CnextPageToken&maxResults=50&prettyPrint=false&q=label%3ANewsletters+after%3A2026-07-24": round trip: base token source: oauth2: "invalid_grant" "Token has been expired or revoked."
```

**Cause**: The Gmail OAuth refresh token remains expired/revoked (`invalid_grant`). This first appeared on 2026-07-16 and has **not** self-recovered — it requires interactive re-authentication.

**Remediation**: Re-authenticate `gog` from an interactive terminal (`gog auth login`, complete the Google consent screen), then re-run the ingestion. Confirm the account still grants the required Gmail scopes.

Both errors are environment/auth issues local to the run host plus one pre-existing code defect (the github adapter's missing response validation, in `knowledge-intake`). Neither was introduced by this run.

## Comparison with prior runs

| Run date   | pinboard | papers | github | email | Total |
|------------|---------:|-------:|-------:|------:|------:|
| 2026-06-14 | 0        | 0      | 100    | 0 (keychain timeout) | 100 |
| 2026-06-28 | 0        | 0      | 100    | 0 (invalid_grant) | 100 |
| 2026-07-26 | 1        | 0 (EINTR) | 0 (TypeError) | 0 (invalid_grant) | 1 |
| **2026-07-27** | **2** | **4** | **0 (TypeError)** | **0 (invalid_grant)** | **6** |

(The 2026-07-26 run is from the uncommitted log `.knowledge-ingest-2026-07-26.log`; no report was filed for it.)

Notable changes since yesterday's run:

- **papers recovered**: yesterday it failed with `EINTR: interrupted system call` scanning the iCloud Papers directory; today it fetched 4 items normally. That failure was transient iCloud Drive sync contention.
- **github still broken**: same masked-401 TypeError. The 2026-06-28 run was the last time github fetched successfully.
- **email still broken**: `invalid_grant` on every run since 2026-07-16.

## Raw log

```text
$ cd ~/dev/knowledge-intake && source .env && bun run src/cli.ts ingest

[pinboard] fetched 2 new items
[papers] fetched 4 new items
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

Ingestion complete: 6 new items

EXIT_CODE=0
```
