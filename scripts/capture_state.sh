#!/usr/bin/env bash
# Generate a capture state tracking template for Intent Layer work
# Usage: ./capture_state.sh [output_file]
#
# Creates a structured markdown file for tracking:
# - Open questions during capture
# - Cross-references pending LCA decision
# - Suspected dead code
# - Deferred tasks
#
# Use with agent-driven capture workflow (references/capture-workflow-agent.md)

set -e

OUTPUT_FILE="${1:-capture_state.md}"
TIMESTAMP=$(date +"%Y-%m-%d")

cat > "$OUTPUT_FILE" << 'TEMPLATE'
# Capture State Tracker

> Track open items during Intent Layer capture. Resolve as you move up the tree.

## Metadata

- **Date Started**: TIMESTAMP_PLACEHOLDER
- **Project**:
- **Capture Order**: (list nodes in planned capture order)

---

## Open Questions

Questions that can't be answered yet. Resolve when capturing neighbor nodes.

| ID | Question | Blocking Node | Expected Resolution |
|----|----------|---------------|---------------------|
| Q1 | | | |
| Q2 | | | |
| Q3 | | | |

**Resolution workflow**:
1. Note which node the question blocks
2. Continue with other captures
3. Return when neighbor capture provides answer
4. Update blocking node and mark resolved

---

## Cross-References (Pending LCA Decision)

Facts that apply to multiple areas. Decide where to place after seeing full picture.

| Fact | Candidate Nodes | Final Location | Decision |
|------|-----------------|----------------|----------|
| | | | TBD |
| | | | TBD |

**LCA decision workflow**:
1. Note the fact and all candidate nodes
2. After capturing candidates, find lowest common ancestor
3. Place fact at LCA, remove from children
4. Update this table with final location

---

## Suspected Dead Code

Code that appears unused but might have hidden dependencies.

| Path | Evidence | Verified? | Verdict |
|------|----------|-----------|---------|
| | No imports found | [ ] | |
| | References old API | [ ] | |
| | Marked deprecated | [ ] | |

**Verification workflow**:
1. Note path and evidence of suspected dead code
2. Ask human to verify (may need grep across repos, check CI, etc.)
3. If dead: delete and don't document
4. If alive: add to Pitfalls ("looks dead but isn't")

---

## Deferred Tasks

Items discovered during capture that aren't blocking but should be addressed.

- [ ]
- [ ]
- [ ]

**Examples**:
- [ ] Consider splitting `src/core/` (approaching 80k tokens)
- [ ] Add ADR link for caching decision when written
- [ ] Revisit auth node after team confirms new flow

---

## Capture Progress

Track which nodes are done.

| Node | Status | Notes |
|------|--------|-------|
| | Not started | |
| | In progress | |
| | Done | |
| | Blocked | Waiting on Q1 |

---

## Session Notes

Free-form notes from capture sessions.

### Session 1 - TIMESTAMP_PLACEHOLDER

(Notes from first capture session)

TEMPLATE

# Replace timestamp placeholder
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/TIMESTAMP_PLACEHOLDER/$TIMESTAMP/g" "$OUTPUT_FILE"
else
    sed -i "s/TIMESTAMP_PLACEHOLDER/$TIMESTAMP/g" "$OUTPUT_FILE"
fi

echo "=== Capture State Tracker Created ==="
echo ""
echo "Output: $OUTPUT_FILE"
echo ""
echo "Use this template to track:"
echo "  - Open questions (resolve when capturing neighbors)"
echo "  - Cross-references (decide LCA after full picture)"
echo "  - Suspected dead code (verify before documenting)"
echo "  - Deferred tasks (address after capture complete)"
echo ""
echo "See references/capture-workflow-agent.md for the full agent-driven workflow."
