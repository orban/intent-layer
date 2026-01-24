#!/usr/bin/env bash
# SessionStart hook - Injects Intent Layer context into agent
# Input: JSON on stdin with session info
# Output: JSON with additionalContext to stdout
#
# Injects (in order of priority):
# 1. First-time setup prompt if no Intent Layer exists
# 2. Recent learnings from accepted mistakes
# 3. Pending mistakes reminder if any exist

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
source "$PLUGIN_ROOT/lib/common.sh"

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"
CONTEXT_PARTS=()

# --- Check 1: Does Intent Layer exist? ---
DETECT_STATE="$PLUGIN_ROOT/scripts/detect_state.sh"
if [[ -x "$DETECT_STATE" ]]; then
    STATE=$("$DETECT_STATE" "$PROJECT_ROOT" 2>/dev/null | grep -oE 'state: (none|partial|complete)' | cut -d' ' -f2 || echo "unknown")

    if [[ "$STATE" == "none" ]]; then
        CONTEXT_PARTS+=("## ⚠️ Intent Layer: Not Configured

No CLAUDE.md or AGENTS.md found in this project.

**Run \`/intent-layer\` to set up AI-friendly navigation:**
- Contracts, patterns, and pitfalls that prevent mistakes
- Automatic learning loop captures gotchas as you work
- Compression ratio ~100:1 vs reading raw code

Without this, I'm navigating blind. Setup takes ~5 minutes for most projects.")
    fi
fi

# --- Check 2: Recent learnings from accepted mistakes ---
AGGREGATE_SCRIPT="$PLUGIN_ROOT/lib/aggregate_learnings.sh"
if [[ -x "$AGGREGATE_SCRIPT" ]]; then
    LEARNINGS=$("$AGGREGATE_SCRIPT" --days 7 --format summary --path "$PROJECT_ROOT" 2>/dev/null || true)

    if [[ -n "$LEARNINGS" ]]; then
        CONTEXT_PARTS+=("## Intent Layer: Recent Learnings

The following mistakes were recently captured and converted to Intent Layer updates.
Be aware of these patterns when working in related areas.

$LEARNINGS")
    fi
fi

# --- Check 3: Pending mistakes that need review ---
PENDING_DIR="$PROJECT_ROOT/.intent-layer/mistakes/pending"
if [[ -d "$PENDING_DIR" ]]; then
    # Count both full reports and skeletons
    PENDING_FILES=$(find "$PENDING_DIR" \( -name "MISTAKE-*.md" -o -name "SKELETON-*.md" \) -type f 2>/dev/null | sort)
    PENDING_COUNT=$(echo "$PENDING_FILES" | grep -c . 2>/dev/null || echo "0")

    if [[ "$PENDING_COUNT" -gt 0 ]]; then
        # Build file list for agent
        FILE_LIST=$(echo "$PENDING_FILES" | while read -r f; do
            [[ -n "$f" ]] && echo "- \`$(basename "$f")\`"
        done)

        CONTEXT_PARTS+=("## Intent Layer: Pending Learning Reports

There are **$PENDING_COUNT pending report(s)** awaiting review:

$FILE_LIST

**Agent: Offer to help the user review these interactively.**

When the user agrees, for each report:
1. **Read** the file and present a summary (type, directory, what was learned)
2. **Analyze** whether it's worth documenting
3. **Ask** the user: Accept, Reject, or Discard?
4. **Execute** based on choice:
   - **Accept**: Run \`${CLAUDE_PLUGIN_ROOT}/lib/integrate_pitfall.sh <file>\`
   - **Reject**: Ask for reason, move to \`$PROJECT_ROOT/.intent-layer/mistakes/rejected/\`
   - **Discard**: \`rm <file>\`

**Proactive capture**: If you discover something worth documenting during this session, use:
\`${CLAUDE_PLUGIN_ROOT}/scripts/capture_mistake.sh --type [pitfall|check|pattern|insight]\`

Pending directory: \`$PENDING_DIR\`")
    fi
fi

# --- Output combined context ---
if [[ ${#CONTEXT_PARTS[@]} -eq 0 ]]; then
    exit 0
fi

# Join all context parts with separators
FULL_CONTEXT=""
for part in "${CONTEXT_PARTS[@]}"; do
    if [[ -n "$FULL_CONTEXT" ]]; then
        FULL_CONTEXT="$FULL_CONTEXT

---

$part"
    else
        FULL_CONTEXT="$part"
    fi
done

output_context "SessionStart" "$FULL_CONTEXT"
