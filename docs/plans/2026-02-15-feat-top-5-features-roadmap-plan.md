---
title: "feat: top 5 features roadmap"
type: feat
date: 2026-02-15
deepened: 2026-02-16
source: docs/brainstorms/2026-02-15-feature-ideas-brainstorm.md
---

# Top 5 Features Roadmap

## Enhancement Summary

**Deepened on:** 2026-02-16
**Sections enhanced:** 5 phases + cross-cutting concerns
**Review agents used:** Architecture Strategist, Performance Oracle, Security Sentinel, Code Simplicity Reviewer, Best Practices Researcher

### Key improvements from review
1. Correlation ID collision risk is ~12.5% (birthday paradox), not 1-in-1M — fixed with timestamp prefix
2. MCP server needs path traversal protection (HIGH security risk)
3. Bash MCP server option proposed to stay consistent with project's "no external deps" philosophy
4. Template manifests simplified from JSON to README-based discovery
5. Phase 4 should parallelize API calls with concurrency limit (14s → 3.5s for 20-node PRs)
6. Cursor deprecated `.cursorrules` — adapter should generate `.cursor/rules/*.mdc` files (YAML frontmatter + markdown)

### New considerations discovered
- Env vars can't pass correlation IDs across hook boundaries — must use temp file
- `$$` in subprocess returns parent PID, not unique-per-request — use `$BASHPID` or timestamp
- Token budget priority order should be format-specific, not hardcoded
- Need standardized exit code contract across all scripts

---

## Overview

Implementation plan for the five highest-priority features identified in the brainstorming swarm. These features share a common foundation (`resolve_context.sh`) and can be built incrementally, each one making the next easier.

## Recommended Build Order

```
Phase 1: Cursorrules Adapter     (small, standalone, immediate value)
Phase 2: MCP Context Server      (medium, strategic, unlocks ecosystem)
Phase 3: Context Telemetry       (small, extends hooks, enables measurement)
Phase 4: Diff-to-Intent Suggester (medium, uses Haiku, depends on telemetry)
Phase 5: Templates Marketplace   (medium, content-heavy, benefits from all above)
```

Why this order:
- Phase 1 is a quick win that proves the "export Intent Layer to other tools" concept
- Phase 2 builds the protocol layer that makes Phase 1's output programmatic
- Phase 3 provides the measurement needed to validate Phase 4's suggestions
- Phase 4 depends on understanding what's injected (Phase 3) to suggest what's missing
- Phase 5 benefits from all prior phases as templates can include adapter configs and telemetry setup

### Build order alternatives considered

The architecture review suggested swapping Phase 1 and 2 (MCP first, adapter consumes it). This avoids refactoring `generate_adapter.sh` when MCP lands. However, Phase 1 is a quick win that validates the concept with zero dependencies, while Phase 2 requires Python or a bash JSON-RPC server. **Keep original order but document that Phase 1 may get refactored when Phase 2 ships.**

---

## Phase 1: Cursorrules / Tool Adapter Generator

### Problem

Cursor, Windsurf, Aider, and other AI tools use their own context formats. Teams with Intent Layer can't share that context outside Claude Code without manually copying content.

### Proposed Solution

New script: `scripts/generate_adapter.sh`

```
generate_adapter.sh <project_root> [options]

Options:
  --format <name>     Output format (cursor, aider, copilot, raw)
  --output <path>     Write to file (default: stdout)
  --sections <list>   Comma-separated sections to include
  --max-tokens <n>    Token budget for output (default: 4000)
  -h, --help          Show help
```

### Technical Approach

1. Call `resolve_context.sh <project_root> <project_root> --compact` to get merged context
2. Format the output based on `--format`:
   - `cursor`: Write `.cursor/rules/*.mdc` files (modern format with YAML frontmatter) + legacy `.cursorrules` fallback
   - `aider`: Write to `.aider.conf.yml` conventions section
   - `copilot`: Write to `.github/copilot-instructions.md`
   - `raw`: Flat markdown (useful for any tool that reads markdown)
3. Respect `--max-tokens` by truncating least-important sections first (Pitfalls > Contracts > Entry Points > Patterns)

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/generate_adapter.sh` | **Create** — main script |
| `references/adapter-formats.md` | **Create** — format specs and examples |
| `CLAUDE.md` | **Modify** — add to Scripts table |

### Acceptance Criteria

- [ ] `generate_adapter.sh /project --format cursor` produces valid `.cursor/rules/*.mdc` files
- [ ] Output includes merged Contracts, Pitfalls, Entry Points from all ancestor nodes
- [ ] Token budget is respected (truncation when over limit)
- [ ] `--help` works, errors go to stderr
- [ ] Works on project with no Intent Layer (exits cleanly with message)
- [ ] Truncation uses 80% of token budget (20% safety margin for bytes/4 inaccuracy)
- [ ] Warning emitted to stderr when content is truncated

### Edge Cases

- Project with 20+ nodes: token budget must truncate gracefully
- Project with only root CLAUDE.md (no children): still produces useful output
- Empty sections: skip rather than output blank headers
- Non-ASCII content: passes through correctly (bytes/4 token estimate is approximate)

### Estimated Effort

Small — 1 session. Core logic is `resolve_context.sh` + format wrapping.

### Research Insights

**Simplicity: Consider shipping `--format raw` only for v1.**
The raw markdown format works with any tool. `.cursorrules` is just plain text anyway. Shipping one format first and adding format-specific wrappers when users ask cuts ~40 lines and avoids guessing at format specs that might change. Counter-argument: `.cursorrules` is the highest-demand format and trivial to add (it's just the raw output in a file).

**Best Practices: Cursor has deprecated `.cursorrules` in favor of `.cursor/rules/*.mdc`.**
Cursor's modern format uses `.mdc` files (markdown with YAML frontmatter) in `.cursor/rules/`. Each file has `description`, `globs`, and `alwaysApply` fields in the frontmatter, with the rule body in markdown below. This maps well to Intent Layer's per-directory AGENTS.md structure: each child node can become a separate `.mdc` file with `globs` scoped to that directory. The adapter should generate `.mdc` files as the primary Cursor output, with a legacy `.cursorrules` single-file fallback via `--legacy-cursorrules` flag.

```yaml
# Example .cursor/rules/api.mdc generated from src/api/AGENTS.md
---
description: API layer contracts and pitfalls
globs: src/api/**
alwaysApply: false
---
[merged content from src/api/AGENTS.md]
```

**Architecture: Token budget priority should be format-specific.**
Different tools benefit from different sections. Cursor cares most about Contracts (coding style), while Aider benefits more from Entry Points (file locations). Move priority logic to `references/adapter-formats.md` and let each format define its own truncation order:

```bash
# In generate_adapter.sh
case "$FORMAT" in
    cursor) PRIORITY="Contracts,Pitfalls,Patterns,Entry Points" ;;
    aider)  PRIORITY="Entry Points,Patterns,Contracts,Pitfalls" ;;
    *)      PRIORITY="Pitfalls,Contracts,Entry Points,Patterns" ;;
esac
```

**Performance: Token counting accuracy.**
The `bytes/4` approximation is 14% off for ASCII code (~3.5 chars/token) and 25-50% off for Unicode comments. Use an 80% budget buffer: `BUDGET_WITH_BUFFER=$((MAX_TOKENS * 4 / 5))`. This prevents exceeding the target tool's context limit at the cost of slightly less content.

**Security: Document trust model.**
Generated adapter files inherit whatever is in AGENTS.md. If someone puts `rm -rf /` in their Contracts section, it gets exported to `.cursorrules`. Add a note in `references/adapter-formats.md`: "The adapter assumes AGENTS.md files are trustworthy. Review generated output before committing."

---

## Phase 2: MCP Context Server

### Problem

LLM tools using Model Context Protocol can't discover or use Intent Layer context programmatically. The filesystem protocol works but requires each tool to know about AGENTS.md conventions.

### Proposed Solution

MCP server exposing three tools and one resource type.

**Tools:**
- `read_intent(project_root, target_path, sections?)` → merged ancestor context
- `search_intent(project_root, query, section?)` → matching nodes and excerpts
- `report_learning(project_root, path, type, title, detail)` → queue a learning report

**Resources:**
- `intent://project/path/to/AGENTS.md` → individual node content

### Technical Approach

Two implementation options:

**Option A: Python MCP server** (recommended for ecosystem compatibility)
- Use the `mcp` Python SDK (`MCPServer` class with `@mcp.tool()` decorators, stdio transport)
- Thin wrapper: each tool shells out to existing bash scripts
- `read_intent` → calls `resolve_context.sh`
- `search_intent` → calls `query_intent.sh`
- `report_learning` → calls `report_learning.sh`
- Resources → read AGENTS.md files directly

**Option B: Bash MCP server** (considered for project philosophy alignment)
- The project has a "no external deps beyond coreutils + bc" philosophy
- MCP is JSON-RPC over stdio — bash + jq can implement the protocol
- Stays consistent but significantly more work to implement JSON-RPC properly

**Decision: Use Python.** The MCP server is a separate entry point (users install it explicitly), not part of the core hook/script infrastructure. The "no external deps" contract applies to scripts that run in hooks, not standalone server processes. Document this boundary clearly.

**MCP SDK pattern (from Context7 docs):**
```python
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("intent-layer")

@mcp.tool()
def read_intent(project_root: str, target_path: str, sections: str = "") -> str:
    """Return merged ancestor context for a path."""
    # shells out to resolve_context.sh
    ...

mcp.run(transport="stdio")
```

### Files to Create/Modify

| File | Action |
|------|--------|
| `mcp/server.py` | **Create** — MCP server implementation |
| `mcp/requirements.txt` | **Create** — `mcp>=1.0` |
| `mcp/README.md` | **Create** — setup, usage, and security model |
| `mcp/AGENTS.md` | **Create** — architecture docs for this subsystem |
| `.claude-plugin/plugin.json` | **Modify** — add MCP server config if plugin format supports it |
| `CLAUDE.md` | **Modify** — document MCP server |

### Configuration

Users add to their MCP config (e.g., `~/.claude/mcp_servers.json`):

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
- [ ] `search_intent` returns matching nodes with excerpts
- [ ] `report_learning` creates a pending report in `.intent-layer/mistakes/pending/`
- [ ] Resources expose individual AGENTS.md files
- [ ] Server starts and responds to MCP protocol initialization
- [ ] Works with Claude Desktop, Zed, and other MCP clients
- [ ] `read_intent()` latency <300ms for typical project (10-node hierarchy)
- [ ] Repeated calls to same path return cached results
- [ ] Server startup time <2 seconds
- [ ] Path traversal attempts return error, not file contents

### Edge Cases

- Project root not set: error with helpful message
- No Intent Layer in project: return empty context with setup suggestion
- Large projects (100+ nodes): pagination or token limits on search results
- Concurrent report_learning calls: must not corrupt files (existing REPORT_ID mechanism handles this)

### Estimated Effort

Medium — 2-3 sessions. The MCP SDK handles protocol; most work is wiring to existing scripts.

### Research Insights

**SECURITY CRITICAL: Path traversal protection.**
The MCP server accepts user-controlled `project_root` and `target_path` parameters. Without validation, attackers could read `/etc/passwd` or write reports to arbitrary paths. This is the highest-severity finding across all reviews.

Required mitigations:
1. **Whitelist allowed projects** via `INTENT_LAYER_ALLOWED_PROJECTS` env var
2. **Canonicalize all paths** with `os.path.realpath()` before passing to bash scripts
3. **Validate containment**: `canonical_target.startswith(canonical_root + os.sep)`
4. **Restrict resources** to files ending in `AGENTS.md` or `CLAUDE.md` only

```python
def validate_path(project_root: str, target_path: str) -> str:
    canonical_root = os.path.realpath(project_root)
    if canonical_root not in ALLOWED_PROJECTS:
        raise SecurityError(f"Project not allowed: {project_root}")
    canonical_target = os.path.realpath(
        os.path.join(canonical_root, target_path) if not os.path.isabs(target_path) else target_path
    )
    if not canonical_target.startswith(canonical_root + os.sep):
        raise SecurityError(f"Path outside project: {target_path}")
    return canonical_target
```

**Architecture: Concurrency safety for report IDs.**
When multiple MCP clients call `report_learning` concurrently, the bash subprocess inherits the Python server's PID (`$$`), not a unique ID. Fix: use `$BASHPID` or pass a unique request ID from Python to the bash script.

**Performance: Add LRU cache for `resolve_context` calls.**
Same path called twice in quick succession shouldn't re-walk the filesystem. Use `functools.lru_cache(maxsize=128)` with mtime-based invalidation.

**Architecture: Error mapping layer needed.**
Bash exit codes (0=success, 1=invalid args, 2=no coverage) need mapping to MCP error responses. Document this contract in `scripts/AGENTS.md`.

---

## Phase 3: Context Relevance Telemetry

### Problem

No signal on whether AGENTS.md files are actually helping. The injection log tracks what's injected but not whether the subsequent edit succeeded or failed.

### Proposed Solution

Extend the existing hook infrastructure to track outcomes.

### Technical Approach

**Current state:**
- PreToolUse hook injects context → logs to `injections.log` (TSV: timestamp, edited_file, covering_node, sections)
- PostToolUse hook tracks edits → but doesn't correlate with injections
- PostToolUseFailure hook captures failures → no correlation with what was injected

**Changes needed:**

1. **Add correlation ID** to injection log entries
   - PreToolUse generates a short ID using timestamp + random suffix
   - Passes it via a temp file to PostToolUse/PostToolUseFailure
   - PostToolUse records: `correlation_id, outcome (success/failure), tool_name`

2. **New log file**: `.intent-layer/hooks/outcomes.log`
   - TSV: `timestamp, correlation_id, tool_name, outcome, edited_file`

3. **New script**: `scripts/show_telemetry.sh`
   - Joins injections.log with outcomes.log on correlation_id
   - Outputs:
     - Per-node success/failure rates
     - Coverage gaps (files edited without any injection)
     - Trend over time (daily/weekly)

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/pre-edit-check.sh` | **Modify** — add correlation ID generation |
| `scripts/post-edit-check.sh` | **Modify** — record outcome with correlation ID |
| `scripts/capture-tool-failure.sh` | **Modify** — record failure with correlation ID |
| `scripts/show_telemetry.sh` | **Create** — telemetry dashboard |
| `.intent-layer/hooks/outcomes.log` | **Created at runtime** |
| `CLAUDE.md` | **Modify** — document telemetry |

### Acceptance Criteria

- [ ] Each injection gets a correlation ID
- [ ] PostToolUse and PostToolUseFailure record outcomes linked to correlation IDs
- [ ] `show_telemetry.sh` outputs per-node success/failure rates
- [ ] Coverage gap report shows files edited without Intent Layer context
- [ ] PreToolUse + correlation ID generation stays <100ms (P50), <500ms (P95)
- [ ] PostToolUse + outcome logging stays <20ms
- [ ] Log rotation triggers before outcomes.log exceeds 5000 lines

### Edge Cases

- Correlation ID collision: mitigated by timestamp prefix (see research insights)
- Tool calls without prior injection: outcome recorded with `no_injection` marker
- Multiple injections before single edit: last-write-wins for correlation
- Log rotation: telemetry script handles missing/empty log files gracefully
- Concurrent edits: temp file race is acceptable for single-user Claude sessions

### Estimated Effort

Small-medium — 1-2 sessions. Mostly extending existing hooks.

### Research Insights

**Architecture CRITICAL: Correlation ID collision rate is ~12.5%, not 1-in-1M.**
The plan originally cited `RANDOM % 1000000` giving 1-in-1M collision rate. This ignores the birthday paradox. With 500 active IDs (log rotates at 1000, keeps last 500) in a 1M space, collision probability is `500^2 / (2 * 10^6)` = 12.5%.

Fix: use timestamp prefix.
```bash
CORR_ID="$(date +%s)-$((RANDOM % 1000))"  # epoch-randomSuffix
```
This makes collisions impossible unless two edits happen in the same second with the same 0-999 suffix (0.1% chance).

**Architecture CRITICAL: Env vars can't pass correlation IDs across hook boundaries.**
PreToolUse runs in shell A, PostToolUse runs in shell B. Claude Code doesn't preserve env vars between hook invocations. Must use temp file:

```bash
# In pre-edit-check.sh:
CORR_ID="$(date +%s)-$((RANDOM % 1000))"
echo "$CORR_ID" > "$PROJECT_ROOT/.intent-layer/hooks/last-correlation.tmp"

# In post-edit-check.sh:
if [[ -f "$PROJECT_ROOT/.intent-layer/hooks/last-correlation.tmp" ]]; then
    CORR_ID=$(cat "$PROJECT_ROOT/.intent-layer/hooks/last-correlation.tmp")
fi
```

**Simplicity: Consider timestamp-based join instead of explicit IDs.**
The simplicity reviewer proposed: join `injections.log` and `outcomes.log` on timestamp + file match (within 1s window), eliminating the correlation ID entirely. This is 95%+ accurate with zero coordination overhead. Trade-off: slightly less precise but 30 fewer lines of hook code. Could be a valid v1 approach, graduating to explicit IDs if accuracy matters.

**Performance: Keep temp file writes fast.**
Temp file creation adds 2-10ms per hook invocation. This is acceptable given the 500ms P95 target. Don't use async/background writes — the complexity isn't worth saving 5ms.

**Security: Add opt-out and .gitignore.**
Telemetry logs capture file paths. Add `.intent-layer/hooks/outcomes.log` to `.gitignore` and provide opt-out via `$PROJECT_ROOT/.intent-layer/disable-telemetry` file.

**Performance: Add log rotation for outcomes.log.**
The plan specifies rotation for `injections.log` (1000 lines → 500) but not for `outcomes.log`. Add the same pattern:
```bash
if [[ $(wc -l < "$LOG_FILE") -gt 5000 ]]; then
    tail -2500 "$LOG_FILE" > "$LOG_FILE.tmp"
    mv "$LOG_FILE.tmp" "$LOG_FILE"
fi
```

---

## Phase 4: Diff-to-Intent Suggester

### Problem

After a PR/merge, developers must manually figure out what to update in AGENTS.md. `detect_changes.sh` finds affected nodes but doesn't suggest what to add.

### Proposed Solution

New script: `scripts/suggest_updates.sh`

```
suggest_updates.sh [base_ref] [head_ref] [options]

Options:
  --dry-run          Show suggestions without calling API
  --output <path>    Write suggestions to file (default: stdout)
  --model <name>     Haiku model ID (default: claude-haiku-4-5-20251001)
  --batch-size <n>   Max concurrent API calls (default: 5)
  -h, --help         Show help
```

### Technical Approach

1. Run `detect_changes.sh base_ref head_ref` to find affected nodes
2. For each affected node:
   a. Get the diff for files in that node's scope: `git diff base_ref..head_ref -- <scope>`
   b. Read the current AGENTS.md content
   c. Call Haiku with structured output:
      ```
      Given this AGENTS.md and these code changes, suggest specific additions.
      Return: [{section: "Pitfalls|Contracts|Patterns", title: "...", body: "..."}]
      ```
   d. Format suggestions as reviewable markdown
3. Output a single markdown file with all suggestions grouped by node

### Output Format

```markdown
# Intent Layer Update Suggestions

Generated from diff: main..HEAD

## scripts/AGENTS.md

### Suggested addition to Pitfalls

> **Stop hook requires jq for stdin parsing**
> The stop-learning-check.sh script fails silently without jq because
> it parses JSON input. Guard with `command -v jq` before processing.

### Suggested addition to Patterns

> **Two-tier classification pattern**
> Use bash heuristics as Tier 1 filter, Haiku API call as Tier 2 classifier.
> Only the Tier 2 result drives the decision. Tier 1 gates expensive API calls.

---
Accept suggestions: Run `integrate_pitfall.sh` with the appropriate learning type.
```

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/suggest_updates.sh` | **Create** — main script |
| `CLAUDE.md` | **Modify** — add to Scripts table |

### Dependencies

- `ANTHROPIC_API_KEY` environment variable (same as stop-learning-check.sh)
- `curl` and `jq` for API calls
- `detect_changes.sh` for node detection
- `resolve_context.sh` for current node content

### Acceptance Criteria

- [ ] Produces actionable suggestions (section, title, body)
- [ ] Groups suggestions by affected AGENTS.md node
- [ ] Works without API key (--dry-run shows affected nodes without suggestions)
- [ ] Parallel processing with concurrency limit (default: 5)
- [ ] 20-node PR completes in <5 seconds
- [ ] Diff truncated to 10k chars per node before API call
- [ ] Output is copy-pasteable into AGENTS.md
- [ ] Rate limit compliance (no 429 errors with default batch-size)

### Edge Cases

- No affected nodes: exit cleanly with "no updates needed"
- API key missing: fall back to dry-run mode with warning
- Haiku returns empty suggestions: skip that node
- Very large diffs: truncate to 10k chars per node scope
- Node doesn't exist yet: suggest creating it

### Estimated Effort

Medium — 2 sessions. Core logic is `detect_changes.sh` + Haiku API call + formatting.

### Research Insights

**Performance CRITICAL: Sequential API calls are too slow for large PRs.**
The original plan specified "sequential calls, not parallel" for rate limiting. But:
- 10-node PR sequential: 10 x 500ms = 5 seconds
- 20-node PR sequential: 20 x 500ms = 10+ seconds (developer abandons the command)

Fix: parallelize with a concurrency limit.
```bash
MAX_PARALLEL=5
PIDS=()
for node in $AFFECTED_NODES; do
    while [[ ${#PIDS[@]} -ge $MAX_PARALLEL ]]; do
        for i in "${!PIDS[@]}"; do
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                unset "PIDS[$i]"
            fi
        done
        sleep 0.1
    done
    (call_haiku_for_node "$node") &
    PIDS+=($!)
done
wait
```

Anthropic's Tier 1 rate limit is 50 req/min, 50k tokens/min. 5 concurrent requests x 2k tokens = 10k tokens/minute — well under limits.

**Security: Pre-scan diffs for secrets before sending to API.**
Diffs may contain credentials, API keys, or tokens. Add a simple regex check before API calls:
```bash
if echo "$DIFF" | grep -qE '(password|secret|api[_-]?key|token)\s*[:=]'; then
    echo "Warning: Diff may contain secrets. Skipping node." >&2
    continue
fi
```

Also filter sensitive files from diffs: `.env`, `credentials.json`, `*.pem`, etc.

**Security: Secure API key storage.**
Document two storage options:
1. `~/.intent-layer/api-key` with 600 permissions (preferred)
2. `ANTHROPIC_API_KEY` env var (existing pattern, less secure)

Validate key file permissions before use.

**Architecture: Add exponential backoff for 429 responses.**
```bash
call_haiku_with_retry() {
    local attempt=1 delay=1
    while [[ $attempt -le 3 ]]; do
        response=$(curl -s -w "%{http_code}" ...)
        http_code="${response: -3}"
        [[ "$http_code" == "200" ]] && echo "${response:0:-3}" && return 0
        [[ "$http_code" == "429" ]] && sleep "$delay" && delay=$((delay * 2))
        attempt=$((attempt + 1))
    done
    return 1
}
```

---

## Phase 5: Templates Marketplace

### Problem

New users face blank-page syndrome. They don't know what a good AGENTS.md looks like for their tech stack.

### Proposed Solution

Curated starter templates in `references/templates/` installable via the `/intent-layer` skill.

### Technical Approach

1. **Template structure**: Each template is a directory with a README and pre-written node files

```
references/templates/
├── nextjs-saas/
│   ├── README.md              # First line: name. Metadata in header.
│   ├── CLAUDE.md.template
│   ├── src/AGENTS.md.template
│   └── src/api/AGENTS.md.template
├── python-ml/
│   ├── README.md
│   ├── CLAUDE.md.template
│   └── ...
├── go-microservice/
│   └── ...
└── rails-monolith/
    └── ...
```

2. **Template variables**: Simple `PROJECT_NAME` placeholder replaced via `sed`
3. **New script**: `scripts/apply_template.sh`

```
apply_template.sh <project_root> <template_name> [options]

Options:
  --list              List available templates
  --preview           Show what would be created (dry-run)
  --force             Overwrite existing files
  --var KEY=VALUE     Set template variable
  -h, --help          Show help
```

4. **Skill integration**: The `/intent-layer` skill detects tech stack and suggests a template

### Starter Templates (v1)

| Template | Stack | Nodes |
|----------|-------|-------|
| `nextjs-saas` | Next.js, React, TypeScript | root + app/ + api/ + lib/ |
| `python-ml` | Python, PyTorch/scikit-learn | root + src/ + data/ + models/ |
| `go-microservice` | Go, gRPC | root + cmd/ + internal/ + pkg/ |
| `rails-monolith` | Ruby on Rails | root + app/models/ + app/controllers/ + app/services/ |
| `generic` | Any stack | root + src/ (minimal, universal) |

### Files to Create/Modify

| File | Action |
|------|--------|
| `scripts/apply_template.sh` | **Create** — template application script |
| `references/templates/*/README.md` | **Create** — per-template description and metadata |
| `references/templates/*/*.template` | **Create** — template files |
| `skills/intent-layer/SKILL.md` | **Modify** — add `--template` flow |
| `CLAUDE.md` | **Modify** — document templates |

### Acceptance Criteria

- [ ] `apply_template.sh /project --list` shows available templates
- [ ] `apply_template.sh /project nextjs-saas --preview` shows what would be created
- [ ] Templates install correctly, creating valid AGENTS.md files
- [ ] Variables are substituted (`PROJECT_NAME` replaced)
- [ ] Won't overwrite existing files without `--force`
- [ ] Each template passes `validate_node.sh`
- [ ] Variable substitution is safe (no shell injection via sed)

### Edge Cases

- Project already has Intent Layer: warn and require `--force`
- Template references directories that don't exist in project: create only matching nodes, skip others
- Unknown template name: list available templates with descriptions
- Template with no variables: works fine (static content)

### Estimated Effort

Medium — 2-3 sessions. Script is straightforward; the work is writing good template content.

### Research Insights

**Simplicity: Replace JSON manifests with README-based discovery.**
The original plan had two levels of JSON manifests (`manifest.json` + per-template `template.json`). This is over-engineered. Templates are directories. Discovery via `ls`, metadata in README headers:

```markdown
# Next.js SaaS
Stack: Next.js, React, TypeScript
Nodes: root, app/, api/, lib/

Starter template for Next.js SaaS applications with App Router...
```

`apply_template.sh --list` reads the first line of each `README.md`. No manifest to maintain, no drift between manifest and actual templates.

**Security: Safe variable substitution.**
Using `sed "s/{{project_name}}/$VALUE/g"` is vulnerable to command injection if `$VALUE` contains special characters. Use safe substitution:

```bash
substitute_variable() {
    local template="$1" var_name="$2" var_value="$3"
    # Escape sed special chars in value
    var_value=$(printf '%s\n' "$var_value" | sed 's/[&/\]/\\&/g')
    sed "s|{{${var_name}}}|${var_value}|g" "$template"
}
```

Better: validate variable names (alphanumeric + underscore only) and sanitize values (remove control characters, limit length to 256 chars).

**Security: Validate template destination paths.**
Template files could use relative paths to write outside the project. Validate that every destination resolves to inside `$PROJECT_ROOT`:
```bash
dest_path=$(realpath -m "$project_root/$dest")
[[ "$dest_path" == "$project_root"/* ]] || exit 1
```

**Simplicity: No variable engine in v1.**
Most template content is boilerplate. Project name appears once in root CLAUDE.md. Ship v1 with static templates (no variables). If needed later, add a single `sed` pass for `PROJECT_NAME`. Don't build a templating engine.

**Architecture: Extend `validate_node.sh` with `--template-mode`.**
Templates need validation too, but `validate_node.sh` checks rendered output. Add a flag that renders with sample values first, then validates:
```bash
validate_node.sh --template-mode path/to/CLAUDE.md.template
```

---

## Dependencies & Prerequisites

| Feature | Depends On | External Deps |
|---------|-----------|---------------|
| Cursorrules Adapter | `resolve_context.sh` (exists) | None |
| MCP Context Server | All existing scripts | Python 3, `mcp` package |
| Context Telemetry | Hook infrastructure (exists) | None |
| Diff-to-Intent Suggester | `detect_changes.sh` (exists), `resolve_context.sh` | `curl`, `jq`, `ANTHROPIC_API_KEY` |
| Templates Marketplace | `validate_node.sh` (exists) | None |

## Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|------------|
| MCP SDK changes | Medium | Pin version, use stable API surface only |
| MCP path traversal | **High** | Whitelist projects, canonicalize paths, validate containment |
| Haiku API costs (Suggester) | Low | Dry-run default, API calls opt-in |
| Template content quality | Medium | Start with 2 templates (generic + one stack), add more based on feedback |
| Hook latency (Telemetry) | High | Correlation via temp file (fast), no API calls in hooks |
| Template injection | Medium | Safe sed substitution, validate variable names, limit value length |
| Cursor format migration | Low | Generate `.mdc` (current) + `.cursorrules` (legacy fallback). `.mdc` format is stable since late 2025. |
| Correlation ID collision | Medium | Timestamp prefix eliminates birthday paradox risk |

## Cross-Cutting Concerns

### Exit code standardization

Standardize across all scripts (document in `scripts/AGENTS.md`):
```
Exit 0: success, output on stdout
Exit 1: invalid input (bad args, missing file), error on stderr
Exit 2: valid input but no result (no coverage, no nodes), explanation on stderr
```

### Concurrency safety

Scripts called via MCP may run concurrently. Key fix: replace `$$` with `$BASHPID` in `capture_mistake.sh` for report ID generation. Or better, use timestamp-based IDs:
```bash
REPORT_ID=$(date +%s%N | tail -c 10)-$(printf "%05d" "$((RANDOM % 100000))")
```

### Privacy and data collection

Document what telemetry logs collect (file paths, timestamps, success/failure). Add `.gitignore` entries for all log files. Provide opt-out via `$PROJECT_ROOT/.intent-layer/disable-telemetry`.

## Success Metrics

- **Cursorrules Adapter**: At least 1 other AI tool successfully using Intent Layer context
- **MCP Server**: Successful connection from 2+ MCP clients
- **Telemetry**: First per-node success/failure report generated
- **Suggester**: Suggestions accepted >50% of the time
- **Templates**: New project setup time drops from ~30 min to ~5 min

## References

- Brainstorm: `docs/brainstorms/2026-02-15-feature-ideas-brainstorm.md`
- Existing agent protocol: `references/agent-protocol.md`
- Template format: `references/templates.md`
- Hook architecture: `hooks/AGENTS.md`
- Script patterns: `scripts/AGENTS.md`
- MCP Python SDK: `MCPServer` class, `@mcp.tool()` decorators, `mcp.run(transport="stdio")`
