#!/usr/bin/env bash
# PreToolUse hook for Edit/Write - Injects pitfalls via additionalContext
# Input: JSON on stdin with tool_name, tool_input
# Output: JSON with additionalContext to stdout

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")}"
source "$PLUGIN_ROOT/lib/common.sh"

INPUT=$(cat)

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

FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"
CHECK_HISTORY="$PLUGIN_ROOT/lib/check_mistake_history.sh"

if [[ ! -f "$FIND_NODE" ]]; then
    exit 0
fi

NODE_PATH=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

if [[ -z "$NODE_PATH" ]]; then
    exit 0
fi

FILE_DIR="$(dirname "$FILE_PATH")"

HIGH_RISK=false
if [[ -f "$CHECK_HISTORY" ]]; then
    if "$CHECK_HISTORY" "$FILE_DIR" &>/dev/null; then
        HIGH_RISK=true
    fi
fi

PITFALLS=$("$FIND_NODE" "$FILE_PATH" --section Pitfalls 2>/dev/null || true)

if [[ -z "$PITFALLS" ]]; then
    exit 0
fi

# Build context message
if $HIGH_RISK; then
    CONTEXT="## Intent Layer Context

**Editing:** \`$FILE_PATH\`
**Covered by:** \`$NODE_PATH\`

**HIGH-RISK AREA** - This directory has a history of mistakes.

Before proceeding, verify these pitfalls don't apply to your change:

$PITFALLS

---
**Pre-flight check:** Confirm you've reviewed the pitfalls above."
else
    CONTEXT="## Intent Layer Context

**Editing:** \`$FILE_PATH\`
**Covered by:** \`$NODE_PATH\`

Relevant pitfalls from covering node:

$PITFALLS"
fi

output_context "PreToolUse" "$CONTEXT"
