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
        CONTEXT_PARTS+=("## Intent Layer: Not Configured

This project doesn't have an Intent Layer yet (no CLAUDE.md or AGENTS.md found).

**Consider running \`/intent-layer\` to:**
- Create a root CLAUDE.md with project overview
- Identify directories that need AGENTS.md coverage
- Set up the learning loop for capturing mistakes

This is optional but helps AI agents navigate your codebase more effectively.")
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
    PENDING_COUNT=$(find "$PENDING_DIR" -name "MISTAKE-*.md" -type f 2>/dev/null | wc -l | tr -d ' ')

    if [[ "$PENDING_COUNT" -gt 0 ]]; then
        CONTEXT_PARTS+=("## Intent Layer: Pending Mistakes

There are **$PENDING_COUNT pending mistake report(s)** awaiting review in:
\`$PENDING_DIR\`

To process them:
1. Review each MISTAKE-*.md file
2. If valid, move to \`accepted/\` and add pitfall to covering AGENTS.md
3. If not valid, move to \`rejected/\`")
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
