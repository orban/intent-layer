#!/usr/bin/env bash
# PreToolUse hook for Read/Grep/Edit/Write — pushes covering AGENTS.md context
# on ANY file access, not just edits. This turns the "pull" model (agent must
# find AGENTS.md) into "push-on-read" (agent gets context when exploring).
#
# Input: JSON on stdin with tool_name, tool_input
# Output: JSON with additionalContext to stdout
#
# Uses the Intent Layer plugin's find_covering_node.sh to locate the
# nearest AGENTS.md, then extracts Pitfalls/Contracts/Patterns sections.

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")}"
source "$PLUGIN_ROOT/lib/common.sh"

INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

TOOL_NAME=$(json_get "$INPUT" '.tool_name' '')

# Extract file path from tool input — different tools use different keys
FILE_PATH=""
case "$TOOL_NAME" in
    Read)
        FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
        ;;
    Grep)
        FILE_PATH=$(json_get "$INPUT" '.tool_input.path' '')
        ;;
    Edit|Write)
        FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
        ;;
    NotebookEdit)
        FILE_PATH=$(json_get "$INPUT" '.tool_input.notebook_path' '')
        ;;
    *)
        exit 0
        ;;
esac

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Skip non-source files (configs, package files, etc.)
case "$FILE_PATH" in
    */../*|../*|*/..|..) exit 0 ;;
    *.json|*.yaml|*.yml|*.toml|*.cfg|*.ini|*.lock) exit 0 ;;
    *node_modules/*|*.git/*|*__pycache__/*) exit 0 ;;
esac

FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"

if [[ ! -f "$FIND_NODE" ]]; then
    exit 0
fi

NODE_PATH=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

if [[ -z "$NODE_PATH" ]]; then
    exit 0
fi

# Extract sections from covering AGENTS.md
extract_section() {
    local section_name="$1"
    awk -v section="$section_name" '
        /^## / {
            if (found) exit
            if ($0 == "## " section) found=1
        }
        found { print }
    ' "$NODE_PATH"
}

PITFALLS=$(extract_section "Pitfalls")
CONTRACTS=$(extract_section "Contracts")
PATTERNS=$(extract_section "Patterns")

# Exit if no content found
if [[ -z "$PITFALLS" && -z "$CONTRACTS" && -z "$PATTERNS" ]]; then
    exit 0
fi

# Build context message
CONTENT=""
[[ -n "$CONTRACTS" ]] && CONTENT="$CONTRACTS"
if [[ -n "$PITFALLS" ]]; then
    [[ -n "$CONTENT" ]] && CONTENT="$CONTENT

"
    CONTENT="${CONTENT}${PITFALLS}"
fi
if [[ -n "$PATTERNS" ]]; then
    [[ -n "$CONTENT" ]] && CONTENT="$CONTENT

"
    CONTENT="${CONTENT}${PATTERNS}"
fi

CONTEXT="## Subsystem Context ($(basename "$(dirname "$NODE_PATH")")/AGENTS.md)

$CONTENT"

output_context "PreToolUse" "$CONTEXT"
