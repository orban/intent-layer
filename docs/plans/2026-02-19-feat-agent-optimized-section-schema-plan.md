---
title: "feat: Agent-optimized AGENTS.md section schema"
type: feat
date: 2026-02-19
prereq: docs/plans/2026-02-18-feat-intent-layer-improvements-plan.md
brainstorm: docs/brainstorms/2026-02-18-intent-layer-improvements-brainstorm.md
---

# Agent-optimized AGENTS.md section schema

## Overview

Replace the current 11-section AGENTS.md generation format with a 5-section agent-optimized format. The current format optimizes for human readers (narrative prose, architecture overviews). The primary consumer is an AI agent that needs operational constraints, not documentation.

This is a product change to the Intent Layer plugin. It's deferred until after the eval harness runs with the current plugin format (see prereq plan), so we have a clean baseline to compare against.

## Problem statement

The eval data shows that Pitfalls and Contracts sections help agents fix bugs, while Overview, Architecture, Code Map, and similar narrative sections are noise. The current generation produces 11 sections, most of which dilute attention without adding actionable information. The `make test` directive (a "commonly used command" that the current format generates) caused a 29pp penalty on graphiti.

## Proposed solution

### New 5-section schema

| Section | Status | Content |
|---|---|---|
| **Boundaries** | Conditional | Import/dependency constraints, module isolation rules |
| **Contracts** | Mandatory | Invariants not in the type system, pre/post conditions |
| **Rules** | Conditional | Imperative sentences from git history, failure modes, targeted test commands |
| **Ownership** | Conditional | File-to-responsibility mapping, "start here for X" entries |
| **Downlinks** | Conditional | Child AGENTS.md pointers |

### Section mapping (old to new)

| Current (11 sections) | Proposed (5 sections) | Notes |
|---|---|---|
| Purpose | *Dropped* | 1-line comment in heading |
| Design Rationale | *Dropped* | Narrative, not actionable |
| Code Map | *Dropped* | Agents discover this by reading |
| Public API | *Dropped* | IDEs/LSP handles better |
| Entry Points | **Ownership** | Merged: file-to-responsibility + entry points |
| Contracts | **Contracts** | Kept: invariants not in type system |
| Pitfalls + Patterns + Checks | **Rules** | Merged into flat imperative list |
| Boundaries (Always/Ask/Never) | **Boundaries** | Repurposed: import/dependency constraints |
| Downlinks | **Downlinks** | Kept: child node pointers |
| External Dependencies | *Dropped* | Rarely actionable for bug fixes |
| Data Flow | *Dropped* | Narrative |

### Format example

```markdown
# graphiti_core/utils/

## Boundaries
- Imports from: graphiti_core.models
- Does not import from: graphiti_core.server, graphiti_core.driver

## Contracts
- All datetime parameters must be UTC-normalized before comparison
- Edge lists can be empty — callers must handle zero-length

## Rules
- Filter falsey values from edge lists before iteration
- API responses can be list or dict; check isinstance before .get()
- FalkorDB returns string IDs for numeric fields
- Test with: pytest tests/unit/test_temporal.py -k test_utc

## Ownership
- temporal_utils.py: datetime normalization, timezone handling
- maintenance/: graph cleanup operations, bulk updates
- Start here for datetime bugs: temporal_utils.py

## Downlinks
| Area | Node | Description |
| maintenance | `maintenance/AGENTS.md` | Graph cleanup, bulk edge operations |
```

### New generation prompt

Replace the current 10-section exploration prompt in SKILL.md (lines 347-394) with:

```
Analyze [DIRECTORY] for an agent-facing AGENTS.md. Return ONLY:

## Boundaries
- What this module imports from (allowed dependencies)
- What must NOT import from this module
- Any isolation rules (e.g., "modules can only import from module_utils")

## Contracts
- Invariants not enforced by the type system
- Pre/post conditions on key functions
- Data format assumptions (e.g., "datetimes must be UTC-normalized")

## Rules
- One imperative sentence per line
- Sourced from: git history (fix/revert commits), known failure modes
- Format: "[WHEN condition] [ALWAYS/NEVER] [action]" or plain imperative
- MAY include targeted test commands (e.g., "test with: pytest tests/unit/test_foo.py")
- MUST NOT include broad commands (e.g., "make test", "pytest", "npm test")

## Ownership
- Map files/directories to responsibilities
- Include "start here for [task]" entries for common operations
- Only non-obvious mappings (skip if directory name = purpose)

## Downlinks
- Child AGENTS.md files below this directory
- One row per child: | Area | Node | Description |

Constraints:
- Maximum 1500 tokens
- Every line must pass: "Would an agent fixing a bug here need this?"

GOOD output (include):
- "Normalize datetimes to UTC before comparison"
- "API responses can be list or dict — check isinstance before .get()"
- "test with: pytest tests/unit/test_temporal.py -k test_utc"
- "graphiti_core.utils imports from: graphiti_core.models only"

BAD output (never generate):
- "This module handles utility functions for the project" (obvious from dir name)
- "make test" or "npm run test" (too broad, causes slow test runs)
- "Follow PEP 8 style guidelines" (linters handle this)
- "The architecture follows a layered pattern with..." (narrative)
- "Be careful when modifying this code" (vague, not actionable)
- "This is a critical component" (significance puffery)
```

Spec conformance: Checked against https://agents.md/ — the spec requires only standard markdown with no mandatory sections. This format is fully conformant.

## Files to modify

| File | Action | What changes |
|---|---|---|
| `references/section-schema.md` | Rewrite | Replace 11-section schema with 5-section schema |
| `skills/intent-layer/SKILL.md` | Modify | Lines 347-394: replace generation prompt with new 5-section prompt |
| `references/templates/generic/CLAUDE.md.template` | Modify | Update section names |
| `references/templates/generic/src/AGENTS.md.template` | Modify | Update section names |
| `references/templates.md` | Modify | Update all template variants |
| `agents/explorer.md` | Modify | Update section references and confidence score targets |
| `scripts/validate_node.sh` | Modify | Lines 178-220: update required sections (child: Contracts required, Rules/Boundaries/Ownership recommended; root: Contracts/Downlinks required) |
| `scripts/pre-edit-check.sh` | Modify | Lines 94-105: extract Rules, Contracts, Boundaries instead of Pitfalls, Checks, Patterns, Context |

## After shipping

1. Regenerate AGENTS.md files for eval repos (graphiti, ansible) using the updated `/intent-layer` skill
2. Commit regenerated files to eval cache
3. Re-run eval with identical configuration (same conditions, same reps)
4. Compare results to the pre-rewrite eval run to measure the effect of the schema change in isolation

## Acceptance criteria

- [ ] SKILL.md generates 5-section AGENTS.md files
- [ ] Generated nodes stay under 1500 tokens
- [ ] pre-edit-check.sh extracts Rules + Contracts + Boundaries from new format
- [ ] validate_node.sh validates new section names
- [ ] All existing tests pass
- [ ] Eval re-run with new format completes and produces comparable results

## References

- Brainstorm: `docs/brainstorms/2026-02-18-intent-layer-improvements-brainstorm.md` (lines 45-153)
- Prerequisite eval plan: `docs/plans/2026-02-18-feat-intent-layer-improvements-plan.md`
- AGENTS.md spec: https://agents.md/
