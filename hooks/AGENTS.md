# hooks/

> 5 hook slots that form the feedback loop: inject learnings before edits, capture failures, prompt for review at session end.

## Purpose

The feedback loop: inject learnings before edits, capture failures, prompt for review at session end.

### Hook slots and data flow

```
SessionStart ─── inject-learnings.sh ───→ Injects recent learnings + state
      │
      ▼
PreToolUse ───── pre-edit-check.sh ─────→ Injects covering AGENTS.md sections
      │                                    Writes to injections.log
      ▼
PostToolUse ──── post-edit-check.sh ────→ Reminds about covered areas
      │
      ▼
PostToolUseFailure ─ capture-tool-failure.sh → Creates skeleton reports
      │                                        Reads injections.log for correlation
      ▼
Stop ──────────── stop-learning-check.sh → Tier 1: heuristic signal check
                                           Tier 2: Haiku classifier (if API key set)
                                           Blocks only on explicit should_capture: true
```

### Injection log

`pre-edit-check.sh` writes to `.intent-layer/hooks/injections.log` on every Edit/Write. Tab-separated format: `timestamp\tfile_path\tcovering_node\tinjected_sections`. `capture-tool-failure.sh` reads this log to determine if a failure happened despite active AGENTS.md guidance. Auto-rotates at 1000 lines (keeps last 500).

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new hook | Add entry to `hooks/hooks.json`, create handler in `scripts/` |
| Modify injection behavior | Edit `scripts/pre-edit-check.sh` |
| Change failure capture | Edit `scripts/capture-tool-failure.sh` |
| Modify Stop hook behavior | Edit `scripts/stop-learning-check.sh` |

## Contracts

- `hooks/hooks.json` is the config boundary and canonical slot list for the repo. Keep matcher order, command wiring, and timeouts aligned there first.
- `lib/common.sh` is the shared payload helper for hook scripts. Use `extract_hook_tool_name`, `extract_hook_file_path`, and `infer_post_tool_use_tool_name` instead of re-implementing field extraction.
- Hooks must complete within their timeout: SessionStart=15s, PreToolUse=10s, PostToolUse=default, PostToolUseFailure=10s, Stop=45s.
- The `<500ms` contract in CLAUDE.md refers to typical execution, not the timeout ceiling.
- Hook scripts read JSON on stdin (except SessionStart which reads nothing). They output JSON via `output_context()`.
- PostToolUse (`post-edit-check.sh`) is the exception — it receives file path as a CLI arg and outputs plain text, not JSON.

### stdin/stdout by hook type

| Hook slot | Matcher | Handler | stdin / CLI payload | stdout |
|-----------|---------|---------|---------------------|--------|
| SessionStart | none | `inject-learnings.sh` | nothing | JSON via `output_context("SessionStart", ...)` |
| PreToolUse | `Edit|Write|NotebookEdit` | `pre-edit-check.sh` | stdin JSON: `tool_name`, `tool_input` | JSON via `output_context("PreToolUse", ...)` |
| PostToolUse | `Edit|Write|NotebookEdit` | `post-edit-check.sh` | CLI arg `$1` with `tool_input` JSON only | plain text |
| PostToolUseFailure | `Edit|Write|NotebookEdit|Bash` | `capture-tool-failure.sh` | stdin JSON: `tool_name`, `tool_input` | JSON via `output_context("PostToolUseFailure", ...)` |
| Stop | none | `stop-learning-check.sh` | stdin JSON: `session_id`, `transcript_path`, `stop_hook_active` | JSON via `output_block(...)` or nothing |

### Canonical payload fields

- Hook slots are the top-level Claude events: `SessionStart`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`.
- Tool names are matcher values inside `PreToolUse`, `PostToolUse`, and `PostToolUseFailure`. They are not hook-slot names.
- Edit-family payloads use the same file selectors across hooks:
  - `Edit` / `Write` → `.tool_input.file_path` (or `.file_path` for the PostToolUse CLI arg)
  - Some write-style payloads may still use `.tool_input.path` / `.path`
  - `NotebookEdit` → `.tool_input.notebook_path` (or `.notebook_path` for PostToolUse)
  - `Bash` → `.tool_input.command` with no file path
- `PostToolUse` is the only transport exception. Claude passes `tool_input` as a CLI string, so the script must infer the tool from payload fields instead of reading `.tool_name`.

## Patterns

### Path extraction varies by tool

Different tools put the file path in different JSON fields, so use the shared helper instead of open-coding the fallback chain:
- `extract_hook_file_path "$INPUT"` for stdin hook payloads
- `extract_hook_file_path "$TOOL_INPUT"` for the PostToolUse CLI arg
- `infer_post_tool_use_tool_name "$TOOL_INPUT"` when PostToolUse telemetry needs `Edit` vs `Write` vs `NotebookEdit`

### Section extraction from AGENTS.md

Pre-edit-check extracts 4 sections: Pitfalls, Checks, Patterns, Context. Uses awk with exact `## Section` matching. Order in output: Checks first (actionable), then Pitfalls, Patterns, Context.

## Pitfalls

### Stop hook fails open by design

The Stop hook (`stop-learning-check.sh`) uses a two-tier architecture: Tier 1 bash heuristics, Tier 2 Haiku API classification. The only path to blocking is an explicit `should_capture: true` from Haiku. All failures (no API key, curl error, timeout, malformed response) exit 0 silently. This is intentional — the previous prompt-based hook was too aggressive and caused JSON validation failures.

### Stop hook requires set +e around curl

The script uses `set -euo pipefail` but the Haiku API call via curl can fail (timeout, connection refused, bad key). Wrap the curl call in `set +e` / `set -e` to prevent the script from dying on API errors. Without this, any API failure kills the script before the fail-open logic runs.

### hooks.json matcher is OR logic, not AND

`"matcher": "Edit|Write|NotebookEdit"` means "if tool_name is Edit OR Write OR NotebookEdit". Omitting `matcher` means the slot applies to that hook event unconditionally (SessionStart, Stop). Don't encode unconditional hooks as `matcher: ""`.

### output_context requires jq

`output_context()` calls `require_jq` internally. If jq isn't installed, hooks that use it will exit 1. This won't crash the session (Claude Code handles hook failures gracefully) but the context won't be injected.

### Injection log only writes when .intent-layer/ exists

`pre-edit-check.sh` checks for `.intent-layer/` before creating the log directory. On projects without an `.intent-layer/` directory, no log is written and no directory is created. This prevents the hook from polluting clean projects.
