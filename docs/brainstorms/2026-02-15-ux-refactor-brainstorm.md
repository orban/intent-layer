# Intent Layer UX Refactor — Brainstorm

Date: 2026-02-15

## What we're building

A full UX overhaul of the intent-layer plugin, restructuring from a flat list of 7 skills into a three-tier architecture (commands → skills → agents), redesigning the learning review pipeline for batch triage, and improving visual output quality across hooks and dashboards.

## Why this approach

The plugin grew organically and now has 7 slash commands with unclear boundaries. Users don't know which to run when. The learning capture pipeline requires 10+ interactions per session for a handful of learnings. Hook outputs dump full AGENTS.md sections before every edit with no deduplication. Dashboard scripts output plain ASCII with no visual hierarchy.

The compound-engineering plugin demonstrates a working three-tier pattern: workflow commands chain skills and spawn agents. We're adopting this pattern while also fixing the review pipeline and output quality.

## Key decisions

### 1. Three-tier reorganization

Restructure the plugin into three tiers:

**Commands** (what users run):
- `/intent-layer` — smart router that detects state and presents the right action
- `/intent-layer:review` — batch learning triage (replaces `/intent-layer-compound` + `/review-mistakes`)
- Workflow sub-commands: `/intent-layer:maintain`, `/intent-layer:health`, `/intent-layer:query`

**Skills** (reusable knowledge, not interactive):
- `node-authoring/` — how to write good AGENTS.md content
- `hierarchy-design/` — T-shaped context, LCA placement, compression
- `learning-loop/` — how the capture → triage → integrate cycle works

**Agents** (already exist, unchanged):
- `explorer.md`, `validator.md`, `auditor.md`, `change-tracker.md`

Old standalone skills (`intent-layer-onboarding`, `intent-layer-health`, `intent-layer-query`) become sub-flows of the router or workflows. No migration aliases — clean break.

### 2. Review pipeline redesign

**Phase 1: Capture (automatic, non-blocking)**
- Stop hook **never blocks session exit**
- Auto-classifies confidence: high / medium / low
- Appends confidence score and suggested section to each skeleton report
- Captures go silently to `.intent-layer/mistakes/pending/`

**Phase 2: Triage (batch, one interaction)**
- `/intent-layer:review` shows ranked table of all pending learnings
- User selects which to accept via `AskUserQuestion` with `multiSelect: true`
- Remaining are discarded or deferred in one action
- Accepted items integrate automatically — no further prompts

**Phase 3: Auto-accept (optional fast path)**
- `--auto-accept-high` flag integrates high-confidence items without prompting
- Only medium/low items shown for review

### 3. Smart router

`/intent-layer` detects state and routes:

| State | Condition | Action |
|-------|-----------|--------|
| none | No CLAUDE.md or AGENTS.md | Offer setup workflow |
| partial | CLAUDE.md exists, no children | Continue setup |
| complete + pending | Learnings waiting | Offer review first |
| complete + stale | Nodes >30 days old | Suggest maintenance |
| complete + healthy | Everything OK | Show menu: maintain, query, export |

Priority order: pending learnings → stale nodes → healthy menu.

### 4. Hook output deduplication

PreToolUse changes:
- Track injected nodes in session-scoped temp file
- First edit to a file: full injection (Pitfalls, Checks, Patterns, Context)
- Same node injected <5 min ago: one-liner summary instead of full content
- High-risk areas (mistake history): always full injection with warning banner

PostToolUse changes:
- Only fire "review if behavior changed" when the edited file is actually referenced in the covering AGENTS.md (check Code Map, Entry Points sections)

### 5. Colon-namespaced naming

| Command | Purpose |
|---------|---------|
| `/intent-layer` | Smart router (main entry point) |
| `/intent-layer:review` | Batch learning triage |
| `/intent-layer:maintain` | Post-change maintenance pass |
| `/intent-layer:health` | Quick validation (staleness + coverage) |
| `/intent-layer:query` | Answer questions using Intent Layer |

Five commands total, all under one namespace. Onboarding becomes a sub-flow of the router (not a standalone command).

### 6. Dashboard color styling

Add ANSI color support with `NO_COLOR` env var opt-out:
- Green for healthy/passing/high rates
- Yellow for warnings/stale/medium confidence
- Red for failures/critical/low rates
- Bold for headers and key metrics
- Dim for secondary info

Add `setup_colors()` helper to `lib/common.sh`. Apply to `show_status.sh`, `show_hierarchy.sh`, `show_telemetry.sh`, and `audit_intent_layer.sh`.

## Open questions

1. Should the smart router also auto-run on SessionStart (via hook) instead of requiring `/intent-layer`?
2. Should `/intent-layer:review` be auto-suggested at session end (non-blocking hint) when there are pending learnings?
3. What confidence threshold separates high from medium? Current stop hook uses a two-tier classifier (heuristic + Haiku) — should the confidence score come from the Haiku response directly?

## Scope exclusions

- MCP server changes (already built, works fine)
- Template system changes (already built)
- Agent restructuring (agents already follow the right pattern)
- Backward-compatible aliases for old skill names (clean break)
