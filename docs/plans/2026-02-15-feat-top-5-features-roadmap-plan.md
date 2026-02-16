---
title: "feat: top 5 features roadmap"
type: feat
date: 2026-02-15
deepened: 2026-02-16
revised: 2026-02-16
source: docs/brainstorms/2026-02-15-feature-ideas-brainstorm.md
---

# Top 5 Features Roadmap

## Revision Notes

**Revised:** 2026-02-16 after review by DHH-style, Kieran-style, and Simplicity reviewers.

Key changes from review:
1. Phase 1 scoped to two formats (cursor + raw), not four
2. Phase 3 uses timestamp-based log join instead of correlation IDs (eliminates temp file coordination and race conditions)
3. Phase 5 ships one template (generic) not five
4. Removed implementation code blocks — those belong in source, not the plan
5. Fixed MCP SDK API (`FastMCP`, not `MCPServer`)
6. Fixed `date +%s%N` portability issue (not available on older macOS)
7. Stripped speculative flags and premature optimizations throughout

---

## Overview

Implementation plan for the five highest-priority features from the brainstorming swarm. They share a common foundation (`resolve_context.sh`) and can be built incrementally.

## Recommended Build Order

```
Phase 1: Tool Adapter Generator    (small, standalone, immediate value)
Phase 2: MCP Context Server        (medium, strategic, unlocks ecosystem)
Phase 3: Context Telemetry         (small, extends hooks, enables measurement)
Phase 4: Diff-to-Intent Suggester  (medium, standalone tool, uses Haiku API)
Phase 5: Templates                 (medium, content-heavy, benefits from all above)
```

Why this order:
- Phase 1 is a quick win that proves the "export Intent Layer to other tools" concept
- Phase 2 builds the protocol layer that makes Phase 1's output programmatic
- Phase 3 provides the measurement needed to validate Phase 4's suggestions
- Phase 4 depends on understanding what's injected (Phase 3) to suggest what's missing
- Phase 5 benefits from all prior phases as templates can include adapter configs and telemetry setup

Note: Phase 1 may get partially refactored when Phase 2 ships (MCP could serve as the adapter's data source). That's fine — ship the quick win first.

---

## Phase 1: Tool Adapter Generator

### Problem

Cursor, Windsurf, Aider, and other AI tools use their own context formats. Teams with Intent Layer can't share that context outside Claude Code without manually copying content.

### Proposed Solution

New script: `scripts/generate_adapter.sh`

```
generate_adapter.sh <project_root> [options]

Options:
  --format <name>     Output format: cursor, raw (default: cursor)
  --max-tokens <n>    Token budget for output (default: 4000)
  --output <path>     Write to file/directory (default: stdout for raw, .cursor/rules/ for cursor)
  -h, --help          Show help
```

v1 ships two formats. More formats (aider, copilot) can be added when users ask for them.

### Technical Approach

1. Walk the Intent Layer hierarchy using `resolve_context.sh`
2. Format the output:
   - `cursor`: Generate `.cursor/rules/*.mdc` files — one per child node, with YAML frontmatter (`description`, `globs`, `alwaysApply`) and markdown body. Root CLAUDE.md becomes `intent-layer-root.mdc` with `alwaysApply: true`.
   - `raw`: Flat merged markdown on stdout (works with any tool that reads markdown; pipe to `.cursorrules`, `.aider.conf.yml`, etc.)
3. Respect `--max-tokens` by dropping lowest-priority sections entirely until under budget. Priority order: Contracts > Pitfalls > Patterns > Entry Points. If the remaining content still exceeds the budget, truncate from the end. Use 80% of the token budget as the effective limit (safety margin for bytes/4 inaccuracy).

For `--format cursor`, the script iterates over child nodes and calls `resolve_context.sh <project_root> <node_directory>` per node to generate scoped `.mdc` files.

Example `.mdc` output:
```yaml
# .cursor/rules/api.mdc generated from src/api/AGENTS.md
---
description: API layer contracts and pitfalls
globs: src/api/**
alwaysApply: false
---
[merged content from src/api/AGENTS.md]
```

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/generate_adapter.sh` | **Create** — main script |
| `CLAUDE.md` | **Modify** — add to Scripts table |

### Acceptance Criteria

- [ ] `generate_adapter.sh /project --format cursor` produces valid `.cursor/rules/*.mdc` files
- [ ] `generate_adapter.sh /project --format raw` outputs merged markdown to stdout
- [ ] Output includes merged Contracts, Pitfalls, Entry Points from ancestor chain
- [ ] Token budget is respected (sections dropped when over limit, warning on stderr)
- [ ] `--help` works, errors go to stderr
- [ ] Works on project with no Intent Layer (exit 2, message on stderr)
- [ ] Running twice produces identical output (idempotent; for cursor format, removes stale `.mdc` files from previous runs)

### Edge Cases

- Project with 20+ nodes: token budget must drop sections gracefully
- Project with only root CLAUDE.md (no children): produces single `.mdc` or raw output
- Empty sections: skip rather than output blank headers
- Non-ASCII content: passes through (bytes/4 estimate is approximate, hence the 80% buffer)

### Estimated Effort

Small — 1 session.

---

## Phase 2: MCP Context Server

### Problem

LLM tools using Model Context Protocol can't discover or use Intent Layer context programmatically.

### Proposed Solution

MCP server exposing two tools and one resource type.

**Tools:**
- `read_intent(project_root, target_path, sections?)` → merged ancestor context
- `report_learning(project_root, path, type, title, detail, agent_id?)` → queue a learning report

**Resources:**
- `intent://project/path/to/AGENTS.md` → individual node content (restricted to AGENTS.md/CLAUDE.md files)

`search_intent` deferred to v2 — MCP clients have their own search patterns, and there's no stated demand.

### Technical Approach

Python MCP server using `FastMCP` from the `mcp` SDK. Thin wrapper — each tool shells out to existing bash scripts.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("intent-layer")

@mcp.tool()
def read_intent(project_root: str, target_path: str, sections: str = "") -> str:
    """Return merged ancestor context for a path."""
    # validates paths, then shells out to resolve_context.sh
    ...

@mcp.tool()
def report_learning(project_root: str, path: str, type: str,
                    title: str, detail: str, agent_id: str = "") -> str:
    """Queue a learning report for later triage."""
    # shells out to report_learning.sh
    ...

mcp.run()
```

**Why Python, not bash:** The MCP server is a separate entry point (users install it explicitly), not part of the core hook/script infrastructure. The "no external deps" contract applies to scripts that run in hooks, not standalone server processes.

**SECURITY: Path traversal protection is mandatory.** The server accepts user-controlled paths. Required mitigations:
1. Whitelist projects via `INTENT_LAYER_ALLOWED_PROJECTS` env var
2. Canonicalize all paths with `os.path.realpath()` before passing to bash scripts
3. Validate containment: `canonical_target.startswith(canonical_root + os.sep)`
4. Validate `target_path` resolves to a directory (for `read_intent`) or to an AGENTS.md/CLAUDE.md file (for resources)

**Error mapping:** Bash exit codes need mapping to MCP error responses. Exit 0 → success, exit 1 → InvalidParams, exit 2 → empty result (not an error). Document in `scripts/AGENTS.md`.

### Files to Create/Modify

| File | Action |
|------|--------|
| `mcp/server.py` | **Create** — MCP server implementation |
| `mcp/requirements.txt` | **Create** — pin `mcp` to actual current version (check PyPI; it's pre-1.0) |
| `CLAUDE.md` | **Modify** — document MCP server |

### Configuration

```json
{
  "intent-layer": {
    "command": "python3",
    "args": ["path/to/intent-layer/mcp/server.py"],
    "env": {
      "INTENT_LAYER_ALLOWED_PROJECTS": "/path/project1:/path/project2"
    }
  }
}
```

### Acceptance Criteria

- [ ] `read_intent` returns merged context matching `resolve_context.sh` output
- [ ] `report_learning` creates a pending report in `.intent-layer/mistakes/pending/`
- [ ] Resources expose individual AGENTS.md files
- [ ] Server starts and responds to MCP protocol initialization
- [ ] Path traversal attempts return error, not file contents
- [ ] Server startup time <2 seconds

### Edge Cases

- Project root not set or not in allowlist: error with helpful message
- No Intent Layer in project: return empty context with setup suggestion
- Concurrent `report_learning` calls: use `$BASHPID` (not `$$`) in subprocess for unique report IDs
- Large projects (100+ nodes): resource listing returns node paths, not full content

### Estimated Effort

Medium — 2-3 sessions. The MCP SDK handles protocol; most work is wiring to existing scripts and getting security right.

---

## Phase 3: Context Telemetry

### Problem

No signal on whether AGENTS.md files are actually helping. The injection log tracks what's injected but not whether the subsequent edit succeeded or failed.

### Proposed Solution

Extend the existing hook infrastructure to track outcomes, then join injection and outcome data at read time.

### Technical Approach

**Current state:**
- PreToolUse hook injects context → logs to `injections.log` (TSV: timestamp, edited_file, covering_node, sections)
- PostToolUse hook tracks edits → no outcome logging
- PostToolUseFailure hook captures failures → no outcome logging

**Changes needed:**

1. **PostToolUse**: append to `.intent-layer/hooks/outcomes.log`
   - TSV: `timestamp, tool_name, outcome (success/failure), edited_file`

2. **PostToolUseFailure**: same, with `outcome=failure`

3. **New script**: `scripts/show_telemetry.sh`
   - Joins `injections.log` and `outcomes.log` on timestamp + file match (within 1s window)
   - No explicit correlation IDs needed — timestamp join is 95%+ accurate for single-user sessions and avoids all cross-hook coordination complexity
   - Outputs per-node success/failure rates, coverage gaps, trend over time

4. **Log rotation**: both logs rotate at 1000 lines (keep last 500), matching the existing `injections.log` pattern. Same threshold prevents orphaned outcomes without matching injections.

5. **Opt-out**: if `$PROJECT_ROOT/.intent-layer/disable-telemetry` exists, hooks skip logging. Add `outcomes.log` to `.gitignore`.

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/post-edit-check.sh` | **Modify** — append outcome to outcomes.log |
| `scripts/capture-tool-failure.sh` | **Modify** — append failure outcome |
| `scripts/show_telemetry.sh` | **Create** — telemetry dashboard |
| `.intent-layer/hooks/outcomes.log` | **Created at runtime** |
| `CLAUDE.md` | **Modify** — document telemetry |

### Acceptance Criteria

- [ ] PostToolUse and PostToolUseFailure record outcomes to `outcomes.log`
- [ ] `show_telemetry.sh` outputs per-node success/failure rates
- [ ] Coverage gap report shows files edited without Intent Layer context
- [ ] Hook modifications stay within existing <500ms contract
- [ ] Log rotation keeps both logs at same threshold (1000 lines → 500)

### Edge Cases

- Tool calls without prior injection: outcome recorded, `show_telemetry.sh` reports as "uncovered edit"
- Multiple rapid edits in same second: timestamp join may mis-pair; acceptable for telemetry accuracy
- Missing/empty log files: `show_telemetry.sh` handles gracefully (reports "no data")

### Estimated Effort

Small — 1 session. Hook changes are a few lines each; `show_telemetry.sh` is the main work.

---

## Phase 4: Diff-to-Intent Suggester

**Note:** This script has external dependencies (curl, jq, ANTHROPIC_API_KEY). It's a standalone tool, not part of the core plugin infrastructure. Consider shipping it as a separate optional script.

### Problem

After a PR/merge, developers must manually figure out what to update in AGENTS.md. `detect_changes.sh` finds affected nodes but doesn't suggest what to add.

### Proposed Solution

New script: `scripts/suggest_updates.sh`

```
suggest_updates.sh [base_ref] [head_ref] [options]

Options:
  --dry-run          Show affected nodes without calling API (default when no API key)
  -h, --help         Show help
```

Concurrency (5 parallel API calls) and model (claude-haiku-4-5-20251001) are hardcoded. Change in source if needed.

### Technical Approach

1. Run `detect_changes.sh base_ref head_ref` to find affected nodes
2. For each affected node, in parallel (max 5 concurrent):
   a. Get scoped diff: `git diff base_ref..head_ref -- <scope>` (truncated to 10k chars)
   b. Read the current AGENTS.md content
   c. Call Haiku for structured suggestions: section, title, body
   d. Retry up to 3 times on 429 responses with backoff
3. Output grouped suggestions as copy-pasteable markdown
4. Filter sensitive files from diffs: `.env`, `credentials.json`, `*.pem`, `*.key`

### Output Format

```markdown
# Intent Layer Update Suggestions

Generated from diff: main..HEAD

## scripts/AGENTS.md

### Suggested addition to Pitfalls

> **Stop hook requires jq for stdin parsing**
> The stop-learning-check.sh script fails silently without jq because
> it parses JSON input. Guard with `command -v jq` before processing.

---
Accept suggestions: Run `integrate_pitfall.sh` with the appropriate learning type.
```

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/suggest_updates.sh` | **Create** — main script |
| `CLAUDE.md` | **Modify** — add to Scripts table |

### Dependencies

- `ANTHROPIC_API_KEY` environment variable
- `curl` and `jq` for API calls
- `detect_changes.sh` for node detection

### Acceptance Criteria

- [ ] Produces actionable suggestions (section, title, body)
- [ ] Groups suggestions by affected AGENTS.md node
- [ ] Works without API key (falls back to dry-run, shows affected nodes only)
- [ ] 20-node PR completes in <5 seconds (5 parallel API calls)
- [ ] Diff truncated to 10k chars per node before API call
- [ ] Output is copy-pasteable into AGENTS.md

### Edge Cases

- No affected nodes: exit 0 with "no updates needed"
- API key missing: dry-run mode with warning
- Haiku returns empty suggestions: skip that node
- Very large diffs: truncated per node scope
- Node doesn't exist yet: suggest creating it

### Estimated Effort

Medium — 2 sessions.

---

## Phase 5: Templates

### Problem

New users face blank-page syndrome. They don't know what a good AGENTS.md looks like for their tech stack.

### Proposed Solution

Starter templates in `references/templates/` installable via `scripts/apply_template.sh`.

### Technical Approach

1. **Template structure**: each template is a directory with static files

```
references/templates/
├── generic/
│   ├── README.md              # First line: display name
│   ├── CLAUDE.md.template     # Static content, no variables
│   └── src/AGENTS.md.template
└── (more templates added based on user feedback)
```

2. **No variable engine in v1.** Templates are static content. If PROJECT_NAME is needed later, a single hardcoded `sed` pass is enough. Don't build a templating engine.

3. **New script**: `scripts/apply_template.sh`

```
apply_template.sh <project_root> <template_name> [options]

Options:
  --list              List available templates (reads first line of each README.md)
  --preview           Show what would be created (dry-run)
  --force             Overwrite existing files
  -h, --help          Show help
```

4. **Skill integration**: The `/intent-layer` skill detects tech stack and suggests a template

### Starter Templates (v1)

Ship `generic` only. Add stack-specific templates based on actual user requests.

| Template | Stack | Nodes |
|----------|-------|-------|
| `generic` | Any stack | root + src/ (minimal, universal) |

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/apply_template.sh` | **Create** — template application script |
| `references/templates/generic/README.md` | **Create** — template description |
| `references/templates/generic/*.template` | **Create** — template files |
| `skills/intent-layer/SKILL.md` | **Modify** — add `--template` flow |
| `CLAUDE.md` | **Modify** — document templates |

### Acceptance Criteria

- [ ] `apply_template.sh /project --list` shows available templates
- [ ] `apply_template.sh /project generic --preview` shows what would be created
- [ ] Templates install correctly, creating valid AGENTS.md files
- [ ] Won't overwrite existing files without `--force`
- [ ] Each template passes `validate_node.sh`
- [ ] Destination paths validated to be inside `$PROJECT_ROOT` (no path traversal via template file paths)

### Edge Cases

- Project already has Intent Layer: warn and require `--force`
- Template references directories that don't exist: create only matching nodes, skip others
- Unknown template name: list available templates

### Estimated Effort

Small — 1 session for script + generic template.

---

## Dependencies & Prerequisites

| Feature | Depends On | External Deps |
|---------|-----------|---------------|
| Tool Adapter | `resolve_context.sh` (exists) | None |
| MCP Context Server | All existing scripts | Python 3, `mcp` package |
| Context Telemetry | Hook infrastructure (exists) | None |
| Diff-to-Intent Suggester | `detect_changes.sh`, `resolve_context.sh` | `curl`, `jq`, `ANTHROPIC_API_KEY` |
| Templates | `validate_node.sh` (exists) | None |

## Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| MCP path traversal | **High** | Whitelist projects, canonicalize paths, validate containment |
| MCP SDK changes | Medium | Pin version, use stable API surface only |
| Haiku API costs (Suggester) | Low | Dry-run default, API calls opt-in |
| Template content quality | Medium | Start with `generic` only, add more from feedback |
| Hook latency (Telemetry) | Low | Just an append to a log file, well under 500ms |
| Cursor format migration | Low | `.mdc` is the only Cursor output; raw format covers legacy needs |

## Exit Code Convention (new scripts only)

New scripts created in this roadmap follow:
```
Exit 0: success, output on stdout
Exit 1: invalid input (bad args, missing file), error on stderr
Exit 2: valid input but no result (no coverage, no nodes), explanation on stderr
```

Existing scripts keep their current exit codes. Retrofitting is a separate task if needed.

## Portability Notes

- `date +%s%N` (nanoseconds) is NOT available on older macOS. Use `date +%s` (epoch seconds) for timestamps. Combine with `$BASHPID` and `$RANDOM` for uniqueness.
- Script naming convention: hook scripts use hyphens (`post-edit-check.sh`), CLI scripts use underscores (`generate_adapter.sh`).

## Success Metrics

- **Tool Adapter**: At least 1 other AI tool successfully using Intent Layer context
- **MCP Server**: Successful connection from 2+ MCP clients
- **Telemetry**: First per-node success/failure report generated
- **Suggester**: Suggestions accepted >50% of the time
- **Templates**: New project setup time drops from ~30 min to ~5 min

## References

- Brainstorm: `docs/brainstorms/2026-02-15-feature-ideas-brainstorm.md`
- Agent protocol: `references/agent-protocol.md`
- Template format: `references/templates.md`
- Hook architecture: `hooks/AGENTS.md`
- Script patterns: `scripts/AGENTS.md`
- MCP Python SDK: `FastMCP` class, `@mcp.tool()` decorators
- Cursor `.mdc` format: `.cursor/rules/*.mdc` with YAML frontmatter (`description`, `globs`, `alwaysApply`)
