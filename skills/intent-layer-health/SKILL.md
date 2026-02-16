---
name: intent-layer:health
description: Quick health check for Intent Layer - validates nodes, checks staleness, reports coverage gaps
argument-hint: "[/path/to/project] [--full]"
---

# Intent Layer Health Check

Quick validation of Intent Layer health before starting work. Run this at session start to catch issues early.

## Quick Start

```bash
# Quick check (default, <30 seconds)
${CLAUDE_PLUGIN_ROOT}/scripts/audit_intent_layer.sh --quick

# Full check (includes consistency analysis)
${CLAUDE_PLUGIN_ROOT}/scripts/audit_intent_layer.sh
```

---

## Workflow

### Quick Check (Default)

Run by default, completes in <30 seconds:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/audit_intent_layer.sh --quick [path]
```

**What it checks:**
- **Validation**: Root node + immediate children only
- **Staleness**: Age of all discovered nodes
- **Coverage**: Directories without covering AGENTS.md

**What it skips:**
- Deep validation of nested nodes
- Section consistency analysis between siblings

### Full Check

Run when user requests `--full` or deeper analysis:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/audit_intent_layer.sh [path]
```

**Additional checks:**
- All nodes validated (not just root + children)
- Section consistency analysis (sibling nodes use same sections)

---

## Interpreting Results

### Status Levels

| Status | Exit Code | Meaning |
|--------|-----------|---------|
| `HEALTHY` | 0 | No issues - good to proceed |
| `NEEDS_ATTENTION` | 1 | Warnings only - can proceed with awareness |
| `CRITICAL` | 2 | Failures or >50% stale nodes - address before work |

### Validation Categories

| Result | Count | Action |
|--------|-------|--------|
| PASS | Nodes with no issues | None |
| WARN | Nodes with warnings | Review, non-blocking |
| FAIL | Nodes with errors | Fix before proceeding |

### Staleness Categories

| Age | Category | Action |
|-----|----------|--------|
| <30 days | Fresh | None |
| 30-90 days | Aging | Monitor |
| >90 days | Stale | Schedule maintenance |

### Coverage

- **80%+**: Good coverage
- **60-80%**: Consider adding nodes for uncovered areas
- **<60%**: Significant gaps - run `/intent-layer:maintain`

---

## Output Format

Present results to user in this format:

```markdown
## Intent Layer Health Check

**Status**: NEEDS_ATTENTION

### Summary
- Validation: 10 PASS, 2 WARN, 0 FAIL
- Staleness: 1 node stale (src/legacy/AGENTS.md - 142 days)
- Coverage: 85% (3 directories uncovered)

### Recommended Actions
1. Run `/intent-layer:maintain` to address stale nodes
2. Consider adding AGENTS.md to: src/utils/, src/migrations/

Ready to proceed with current work? The warnings are informational.
```

---

## Recommendations by Status

### HEALTHY

```markdown
Intent Layer is healthy. Good to proceed with current work.
```

### NEEDS_ATTENTION

```markdown
### Recommended Actions
1. [If stale nodes] Run `/intent-layer:maintain` to update stale nodes
2. [If low coverage] Consider adding AGENTS.md to: [list uncovered directories]
3. [If validation warnings] Review warnings: [list]

These are informational - you can proceed with current work.
```

### CRITICAL

```markdown
### Immediate Actions Required
1. [If validation failures] Fix these nodes before proceeding:
   - [node path]: [issue description]
2. [If >50% stale] Most nodes are outdated - run `/intent-layer:maintain`

Recommend addressing these issues before starting new work.
```

---

## Integration Notes

### Session Start

This skill can be run proactively at session start:
- Quick check is non-blocking (warnings don't stop work)
- Provides awareness of Intent Layer health before diving into tasks
- Pairs well with SessionStart hook for automatic invocation

### CI Integration

For automated checks, use JSON output:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/audit_intent_layer.sh --json --quick
```

Exit codes enable CI pass/fail:
- Exit 0: HEALTHY - pipeline passes
- Exit 1: NEEDS_ATTENTION - pipeline passes with warning
- Exit 2: CRITICAL - pipeline fails

### Related Skills

| Skill | Use When |
|-------|----------|
| `/intent-layer:maintain` | Status is NEEDS_ATTENTION or CRITICAL |
| `/intent-layer` | No Intent Layer exists (state = none/partial) |
| `/intent-layer-query` | Need to query Intent Layer for information |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `audit_intent_layer.sh` | Main audit script (validation, staleness, coverage, consistency) |
| `validate_node.sh` | Single node validation (called by audit) |
| `detect_staleness.sh` | Detailed staleness analysis |
| `detect_state.sh` | Check if Intent Layer exists |

All paths: `${CLAUDE_PLUGIN_ROOT}/scripts/`
