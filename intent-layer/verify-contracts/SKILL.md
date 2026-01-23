---
name: verify-contracts
description: >
  Use when verifying code compliance with Intent Layer contracts before commit,
  during PR review, or on-demand - detects violations and categorizes them as
  code fixes needed, Intent Layer updates, or human decisions.
argument-hint: "[--full] [--thorough] [--path DIR]"
---

# Verify Contracts

Semantic verification of Intent Layer contracts using hierarchical subagent dispatch.

## Quick Start

```bash
# Verify changed files (default)
/verify-contracts

# Verify entire codebase
/verify-contracts --full

# Verify specific directory
/verify-contracts --path src/

# Thorough mode (higher model tiers)
/verify-contracts --thorough
```

## Workflow

### Phase 1: Discovery

Run the bash helper to map nodes, contracts, and files:

```bash
../scripts/discover_contracts.sh --scope changed
```

This outputs JSON with:
- All Intent Layer nodes (CLAUDE.md/AGENTS.md)
- Extracted contracts from each node
- Files covered by each node
- Complexity estimate and recommended model

### Phase 2: Verification

For each node with covered files, dispatch a subagent:

| Complexity | Model | Criteria |
|------------|-------|----------|
| Low | haiku | ≤3 contracts AND ≤5 files |
| Medium | sonnet | ≤6 contracts AND ≤15 files |
| High | sonnet | >6 contracts OR >15 files OR CRITICAL |

With `--thorough`, bump each tier up one level.

**Subagent task**: Read contracts + covered code, determine compliance.

Use prompt template: `./references/subagent-prompt.md`

**Parallelize**: Nodes at the same tree depth can run concurrently.

### Phase 3: Aggregation

Collect subagent results and build tree structure:

1. Roll up results from leaves to root
2. Categorize each violation
3. Count totals per category

### Phase 4: Reporting

Output hybrid tree + test-failure format (see Output Format below).

## Violation Categories

| Category | Meaning | Action |
|----------|---------|--------|
| `CODE_FIX_NEEDED` | Code clearly violates contract | Fix the code |
| `INTENT_LAYER_STALE` | Many files share same "violation" | Update the contract |
| `HUMAN_DECISION` | Ambiguous or edge case | Escalate for judgment |

**Categorization heuristics**:
- Single file violates widely-followed contract → `CODE_FIX_NEEDED`
- >50% of covered files "violate" same contract → `INTENT_LAYER_STALE`
- Contract language is ambiguous → `HUMAN_DECISION`

## Output Format

```
Intent Layer Verification Report
================================

[PASS|FAIL] CLAUDE.md (X violations, Y unclear)
│
├── [PASS|FAIL]: Contract text here
│   │
│   │  Contract (CLAUDE.md:95):
│   │  │ - Scripts must use set -euo pipefail
│   │
│   │  Violation (path/to/file.sh:1-5):
│   │  │ #!/usr/bin/env bash
│   │  │ # Missing: set -euo pipefail
│   │
│   │  Category: CODE_FIX_NEEDED
│   │  Reason: Contract is clear, violation is unambiguous
│   │
│   └── [PASS|FAIL] child/AGENTS.md (N violations)
│       └── ...

Summary: X violations (Y code fixes, Z stale contracts, W human decisions)
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All contracts pass |
| 1 | Violations found |
| 2 | Errors during verification |

## Integration Points

- **Pre-commit**: Run with default scope (changed files)
- **PR review**: Integrate with `/pr-review` workflow
- **CI pipeline**: Run with `--full` on main branch merges

## Related

| Resource | Purpose |
|----------|---------|
| `../scripts/discover_contracts.sh` | Mechanical discovery (bash) |
| `./references/subagent-prompt.md` | Verification prompt template |
| `/pr-review` | PR review workflow (uses this skill) |
| `validate_node.sh` | Node quality validation |
