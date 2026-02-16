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
Stop ──────────── (prompt-based) ───────→ Reviews skeletons + session discoveries
                                           Calls learn.sh to write back
```

### Injection log

`pre-edit-check.sh` writes to `.intent-layer/hooks/injections.log` on every Edit/Write. Tab-separated format: `timestamp\tfile_path\tcovering_node\tinjected_sections`. `capture-tool-failure.sh` reads this log to determine if a failure happened despite active AGENTS.md guidance. Auto-rotates at 1000 lines (keeps last 500).

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new hook | Add entry to `hooks/hooks.json`, create handler in `scripts/` |
| Modify injection behavior | Edit `scripts/pre-edit-check.sh` |
| Change failure capture | Edit `scripts/capture-tool-failure.sh` |
| Adjust Stop prompt | Edit the `prompt` field in `hooks/hooks.json` Stop section |

## Contracts

- Hooks must complete within their timeout: SessionStart=15s, PreToolUse=10s, PostToolUse=default, PostToolUseFailure=10s, Stop=30s.
- The `<500ms` contract in CLAUDE.md refers to typical execution, not the timeout ceiling.
- Hook scripts read JSON on stdin (except SessionStart which reads nothing). They output JSON via `output_context()`.
- PostToolUse (`post-edit-check.sh`) is the exception — it receives file path as a CLI arg and outputs plain text, not JSON.

### stdin/stdout by hook type

| Hook | stdin | stdout |
|------|-------|--------|
| SessionStart | nothing | JSON (output_context) |
| PreToolUse | JSON (tool_name, tool_input) | JSON (output_context) |
| PostToolUse | JSON string as CLI arg (`$1`) | plain text |
| PostToolUseFailure | JSON (tool_name, tool_input) | JSON (output_context) |
| Stop | prompt-based (no script) | JSON ({ok: true/false}) |

## Patterns

### Path extraction varies by tool

Different tools put the file path in different JSON fields:
- Edit/Write → `.tool_input.file_path`
- NotebookEdit → `.tool_input.notebook_path`
- Bash → `.tool_input.command` (no file_path)

Always check multiple fields with fallback: `FILE_PATH=$(json_get ... 'file_path' ''); FILE_PATH=${FILE_PATH:-$(json_get ... 'notebook_path' '')}`.

### Section extraction from AGENTS.md

Pre-edit-check extracts 4 sections: Pitfalls, Checks, Patterns, Context. Uses awk with exact `## Section` matching. Order in output: Checks first (actionable), then Pitfalls, Patterns, Context.

## Pitfalls

### Stop hook JSON response bypassed when agent acts directly

The Stop hook prompt expects {"ok": true/false} JSON responses, but agents may respond with natural language and tool calls instead (e.g., running learn.sh directly). This causes 'JSON validation failed'. The hook design assumes the agent will suggest actions via the reason field, not execute them inline.

_Source: learn.sh | added: 2026-02-15_

### hooks.json matcher is OR logic, not AND

`"matcher": "Edit|Write|NotebookEdit"` means "if tool_name is Edit OR Write OR NotebookEdit". No matcher = applies to all events (SessionStart, Stop).

### Stop hook is a prompt, not a script

The Stop hook uses `"type": "prompt"` with inline text, not `"type": "command"`. It runs as an LLM evaluation, not a bash script. The prompt is a long single-line JSON string — editing it is error-prone. Be careful with JSON escaping.

### output_context requires jq

`output_context()` calls `require_jq` internally. If jq isn't installed, hooks that use it will exit 1. This won't crash the session (Claude Code handles hook failures gracefully) but the context won't be injected.

### Injection log only writes when .intent-layer/ exists

`pre-edit-check.sh` checks for `.intent-layer/` before creating the log directory. On projects without an `.intent-layer/` directory, no log is written and no directory is created. This prevents the hook from polluting clean projects.
