#!/usr/bin/env bash
# PreToolUse hook for Edit/Write - Injects learnings via additionalContext
# Input: JSON on stdin with tool_name, tool_input
# Output: JSON with additionalContext to stdout
#
# Injects all 4 learning types from covering AGENTS.md:
#   - Pitfalls: Things that went wrong / gotchas to avoid
#   - Checks: Pre-action verifications needed
#   - Patterns: Preferred approaches / better ways
#   - Context: Important background knowledge

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
source "$PLUGIN_ROOT/lib/common.sh"

INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

TOOL_NAME=$(json_get "$INPUT" '.tool_name' '')

# The matcher in hooks.json handles tool filtering, but double-check
case "$TOOL_NAME" in
    Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
FILE_PATH=${FILE_PATH:-$(json_get "$INPUT" '.tool_input.path' '')}
# Handle NotebookEdit which uses notebook_path
FILE_PATH=${FILE_PATH:-$(json_get "$INPUT" '.tool_input.notebook_path' '')}

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Basic path sanity check - silent exit for suspicious paths
case "$FILE_PATH" in
    */../*|../*|*/..|..) exit 0 ;;
esac

FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"
CHECK_HISTORY="$PLUGIN_ROOT/lib/check_mistake_history.sh"

if [[ ! -f "$FIND_NODE" ]]; then
    exit 0
fi

NODE_PATH=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

# If no covering node found, warn about uncovered directory
if [[ -z "$NODE_PATH" ]]; then
    # Only warn for source files, not configs/docs
    case "$FILE_PATH" in
        *.ts|*.js|*.tsx|*.jsx|*.py|*.go|*.rs|*.java|*.rb|*.sh)
            CONTEXT="## Intent Layer: Uncovered Directory

**Editing:** \`$FILE_PATH\`
**Coverage:** ⚠️ No covering AGENTS.md found

This directory isn't documented in the Intent Layer. Consider:
- Adding an AGENTS.md if this is a key module
- Running \`/intent-layer-maintenance\` to review coverage"
            output_context "PreToolUse" "$CONTEXT"
            ;;
    esac
    exit 0
fi

FILE_DIR="$(dirname "$FILE_PATH")"

HIGH_RISK=false
if [[ -f "$CHECK_HISTORY" ]]; then
    if "$CHECK_HISTORY" "$FILE_DIR" &>/dev/null; then
        HIGH_RISK=true
    fi
fi

# Extract a section from the node file (including header line)
# Usage: extract_section "Section Name"
extract_section() {
    local section_name="$1"
    awk -v section="$section_name" '
        /^## / {
            if (found) exit
            if ($0 == "## " section) {
                found=1
                print
                next
            }
        }
        found { print }
    ' "$NODE_PATH"
}

# Extract all 4 learning sections from the covering node
PITFALLS=""
CHECKS=""
PATTERNS=""
CONTEXT_SECTION=""

if [[ -n "$NODE_PATH" && -r "$NODE_PATH" ]]; then
    PITFALLS=$(extract_section "Pitfalls")
    CHECKS=$(extract_section "Checks")
    PATTERNS=$(extract_section "Patterns")
    CONTEXT_SECTION=$(extract_section "Context")
fi

# Exit if no learnings found
if [[ -z "$PITFALLS" && -z "$CHECKS" && -z "$PATTERNS" && -z "$CONTEXT_SECTION" ]]; then
    exit 0
fi

# Build context message with all non-empty sections
LEARNINGS=""

if [[ -n "$CHECKS" ]]; then
    LEARNINGS="$CHECKS"
fi

if [[ -n "$PITFALLS" ]]; then
    if [[ -n "$LEARNINGS" ]]; then
        LEARNINGS="$LEARNINGS

$PITFALLS"
    else
        LEARNINGS="$PITFALLS"
    fi
fi

if [[ -n "$PATTERNS" ]]; then
    if [[ -n "$LEARNINGS" ]]; then
        LEARNINGS="$LEARNINGS

$PATTERNS"
    else
        LEARNINGS="$PATTERNS"
    fi
fi

if [[ -n "$CONTEXT_SECTION" ]]; then
    if [[ -n "$LEARNINGS" ]]; then
        LEARNINGS="$LEARNINGS

$CONTEXT_SECTION"
    else
        LEARNINGS="$CONTEXT_SECTION"
    fi
fi

# Build final context message
if $HIGH_RISK; then
    CONTEXT="## Intent Layer Context

**Editing:** \`$FILE_PATH\`
**Covered by:** \`$NODE_PATH\`

**⚠️ HIGH-RISK AREA** - This directory has a history of mistakes.

Before proceeding, review the learnings below carefully:

$LEARNINGS

---
**Pre-flight check:** Confirm you've reviewed the sections above."
else
    CONTEXT="## Intent Layer Context

**Editing:** \`$FILE_PATH\`
**Covered by:** \`$NODE_PATH\`

$LEARNINGS"
fi

output_context "PreToolUse" "$CONTEXT"
