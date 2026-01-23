# verify-contracts Skill Design

> **TL;DR**: Claude-driven semantic verification of Intent Layer contracts, using hierarchical subagent dispatch with complexity-based model selection.

## Overview

A skill that verifies whether code complies with Intent Layer contracts (CLAUDE.md/AGENTS.md assertions). Unlike keyword matching, this uses Claude agents to semantically interpret contracts and reason about compliance.

## Key Decisions

| Decision | Choice |
|----------|--------|
| Trigger | Core engine usable from multiple contexts (pre-commit, on-demand, PR review) |
| Scope | Configurable: changed files (default) or full (`--full`) |
| Model selection | Complexity-based: haiku (simple), sonnet (moderate), opus (complex) |
| Output format | Hybrid tree structure with test-failure formatting |
| Post-violation | Report + categorize (code fix / Intent Layer update / human decision) |
| Invocation | Skill + bash helper (bash for discovery, Claude for reasoning) |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    /verify-contracts skill                   │
│  (orchestrates discovery, dispatches subagents, aggregates)  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │ discover.sh │   │  Subagent   │   │  Subagent   │
    │ (bash)      │   │  (haiku)    │   │  (sonnet)   │
    │ - find nodes│   │  - verify   │   │  - verify   │
    │ - map files │   │    leaf     │   │    complex  │
    │ - estimate  │   │    node     │   │    node     │
    │   complexity│   └─────────────┘   └─────────────┘
    └─────────────┘           │               │
                              └───────┬───────┘
                                      ▼
                         ┌─────────────────────────────────┐
                         │   Result Aggregator (main skill) │
                         │   - tree rollup                  │
                         │   - categorization               │
                         │   - final report                 │
                         └─────────────────────────────────┘
```

**Flow**:
1. Skill invokes `discover.sh` to find Intent Layer nodes and map files
2. Bash helper estimates complexity per node (contracts × files × ambiguity signals)
3. Skill dispatches parallel subagents, selecting model per node's complexity
4. Each subagent reads its node's contracts + covered code, reasons about compliance
5. Results roll up through the tree hierarchy
6. Main skill aggregates, categorizes violations, and produces final report

## Bash Helper: discover.sh

**Purpose**: Mechanical discovery and mapping (no LLM reasoning needed)

**Inputs**:
- `--scope changed|full` - What files to check
- `--base REF` - Git ref for comparison (default: origin/main)
- `--format json` - Output format for skill consumption

**Output** (JSON):
```json
{
  "nodes": [
    {
      "path": "CLAUDE.md",
      "depth": 0,
      "parent": null,
      "contracts": ["Scripts must use set -euo pipefail", "..."],
      "contract_count": 6,
      "covered_files": ["intent-layer/scripts/test_violation.sh"],
      "file_count": 3,
      "complexity": "low",
      "recommended_model": "haiku"
    }
  ],
  "tree": {
    "CLAUDE.md": ["intent-layer/AGENTS.md"]
  }
}
```

**Complexity estimation**:
- `low`: ≤3 contracts AND ≤5 files → haiku
- `medium`: ≤6 contracts AND ≤15 files → sonnet
- `high`: >6 contracts OR >15 files OR contains "CRITICAL" → sonnet/opus

## Subagent Verification Protocol

Each subagent verifies ONE Intent Layer node with focused context:

**Input prompt**:
```
You are verifying Intent Layer contracts for: {node_path}

## Contracts to Verify
{contracts extracted from the node}

## Code to Check
{file contents for covered files}

## Task
For each contract, determine:
1. PASS - Code complies
2. FAIL - Code violates
3. UNCLEAR - Cannot determine

For FAIL, provide:
- Contract text and location (file:line)
- Violation location (file:line)
- Code snippets
- Category: CODE_FIX_NEEDED | INTENT_LAYER_STALE | HUMAN_DECISION
- Reasoning
```

**Category heuristics**:
- Single file violates widely-followed contract → `CODE_FIX_NEEDED`
- Many files share same "violation" → `INTENT_LAYER_STALE`
- Contract is ambiguous → `HUMAN_DECISION`

## Output Format

Hybrid tree structure with test-failure formatting:

```
Intent Layer Verification Report
================================

❌ CLAUDE.md (2 violations, 1 unclear)
│
├── ❌ FAIL: Scripts must use set -euo pipefail
│   │
│   │  Contract (CLAUDE.md:95):
│   │  │ - Scripts use `set -euo pipefail` for robust error handling
│   │
│   │  Violation (intent-layer/scripts/test_violation.sh:1-5):
│   │  │ #!/usr/bin/env bash
│   │  │ # A test script with intentional violations
│   │  │ # ← Missing: set -euo pipefail
│   │
│   │  Category: CODE_FIX_NEEDED
│   │  Reason: Contract is clear, violation is unambiguous
│   │
│   └── ❌ intent-layer/AGENTS.md (1 violation)
│       └── FAIL: ...

Summary: 3 violations (2 code fixes needed, 1 human decision)
Exit code: 1
```

**Exit codes**:
- 0 = all pass
- 1 = violations found
- 2 = errors during verification

## File Structure

```
intent-layer/
├── verify-contracts/
│   ├── SKILL.md              # Main skill (orchestration)
│   └── references/
│       └── subagent-prompt.md  # Template for verification subagents
└── scripts/
    └── discover_contracts.sh   # Bash helper for discovery
```

## Usage Examples

```bash
# On-demand verification of changed files
/verify-contracts

# Full verification of entire codebase
/verify-contracts --full

# Verify specific directory
/verify-contracts --path src/

# Thorough mode (bump model tiers)
/verify-contracts --thorough
```

## Integration Points

- **Pre-commit hook**: Run with `--scope changed --exit-code`
- **PR review**: Integrate with existing `/review-pr` workflow
- **CI pipeline**: Run with `--full` on main branch merges
