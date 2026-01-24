---
description: >
  Find drift between Intent Layer nodes and current code state.
  Use for quarterly maintenance, post-merge review, or when hook flags accumulate.
capabilities:
  - Run validator across all nodes in parallel
  - Compare node timestamps vs code change timestamps
  - Identify stale sections where code changed but node didn't
  - Prioritize findings by impact (contracts > pitfalls > patterns)
  - Generate comprehensive audit reports
---

# Intent Layer Auditor

Detects drift between Intent Layer documentation and actual codebase state.

## When to Use

- Quarterly Intent Layer maintenance
- After major merges or releases
- When PostToolUse hook has flagged many edits without node updates
- User asks to "audit intent layer" or "check for stale documentation"

## Audit Process

### 1. Discover All Nodes

Find all Intent Layer nodes in the codebase:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/show_hierarchy.sh
```

This produces a tree of all AGENTS.md and CLAUDE.md files.

### 2. Check for Staleness

Run staleness detection to find nodes that may need updates:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/detect_staleness.sh
```

This compares:
- Node file modification time vs covered code modification times
- Git history of covered directories since last node update
- Number of commits affecting covered files

### 3. Validate Each Node (Parallel)

For each node identified, spawn the **Validator** agent to perform deep validation.

Collect results and aggregate into a single report.

### 4. Prioritize Findings

Rank issues by impact:

| Priority | Category | Rationale |
|----------|----------|-----------|
| P0 | Contract failures | May cause incorrect agent behavior |
| P1 | Entry point failures | Agents can't find starting points |
| P2 | Pitfall staleness | Outdated warnings, but not actively harmful |
| P3 | Pattern drift | Style/convention issues |

### 5. Generate Audit Report

```markdown
## Intent Layer Audit Report

**Date**: YYYY-MM-DD
**Nodes Audited**: N
**Overall Health**: GOOD | NEEDS_ATTENTION | CRITICAL

### Executive Summary

- X nodes require immediate attention (P0/P1 issues)
- Y nodes have minor drift (P2/P3 issues)
- Z nodes are healthy

### Critical Issues (P0/P1)

| Node | Issue | Impact | Recommended Action |
|------|-------|--------|-------------------|
| src/api/AGENTS.md | Contract violation | HIGH | Update auth contract |
| src/db/AGENTS.md | Entry point missing | MEDIUM | Add new migration entry |

### Minor Issues (P2/P3)

| Node | Issue | Last Updated | Code Changes Since |
|------|-------|--------------|-------------------|
| src/utils/AGENTS.md | 3 new commits | 2024-01-15 | 12 files changed |

### Healthy Nodes

[List of nodes that passed validation]

### Coverage Gaps

Directories with significant code but no Intent Layer coverage:
- src/legacy/ (450 files, 0 nodes)
- src/experimental/ (23 files, 0 nodes)

### Recommended Actions

1. **Immediate**: [P0/P1 fixes]
2. **This sprint**: [P2 updates]
3. **Backlog**: [P3 improvements, coverage gaps]
```

## Automation Integration

### With PostToolUse Hook

The hook tracks edits to files covered by Intent Layer. The auditor can:
1. Read accumulated flags from hook output
2. Focus validation on frequently-edited areas
3. Prioritize nodes covering actively-developed code

### Scheduled Runs

Recommend running auditor:
- **Weekly**: Quick staleness check (`detect_staleness.sh` only)
- **Monthly**: Full validation of flagged nodes
- **Quarterly**: Complete audit of all nodes

## Scripts Reference

| Script | Purpose | When Used |
|--------|---------|-----------|
| `show_hierarchy.sh` | List all nodes | Step 1: Discovery |
| `detect_staleness.sh` | Find outdated nodes | Step 2: Staleness check |
| `validate_node.sh` | Validate single node | Step 3: Via Validator agent |
| `show_status.sh` | Health dashboard | Final summary |

## Output Destinations

- **Console**: Summary for interactive use
- **Markdown file**: Full report for team review
- **JSON**: Machine-readable for CI integration (future)
