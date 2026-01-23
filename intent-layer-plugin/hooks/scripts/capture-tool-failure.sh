#!/usr/bin/env bash
# PostToolUseFailure hook - Suggests mistake capture on tool failures
# Input: JSON on stdin with tool_name, tool_input, etc.
# Output: stderr message (exit 0 = non-blocking suggestion)

set -euo pipefail

# Source shared library
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")}"
source "$PLUGIN_ROOT/lib/common.sh"

# Read hook input
INPUT=$(cat)

# Extract fields
TOOL_NAME=$(json_get "$INPUT" '.tool_name' 'unknown')
FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
FILE_PATH=${FILE_PATH:-$(json_get "$INPUT" '.tool_input.notebook_path' '')}
COMMAND=$(json_get "$INPUT" '.tool_input.command' '')

# Build context string for the suggestion
CONTEXT=""
if [[ -n "$FILE_PATH" ]]; then
    CONTEXT="File: $FILE_PATH"
elif [[ -n "$COMMAND" ]]; then
    CONTEXT="Command: ${COMMAND:0:50}..."
fi

# Skip expected/exploratory failures
case "$TOOL_NAME" in
    Read|Glob|Grep|LS)
        # File exploration failures are expected - silent exit
        exit 0
        ;;
    Bash)
        # Skip common exploratory bash failures
        # (We can't see the error message, but Bash failures during exploration are common)
        # Be conservative - only suggest capture for file-modifying operations
        if [[ -z "$FILE_PATH" ]]; then
            exit 0
        fi
        ;;
esac

# For significant failures (Edit, Write, NotebookEdit, Bash with file_path), output to stderr
# Exit 0 = non-blocking, stderr shown in verbose mode
{
    echo ""
    echo "⚠️ Tool '$TOOL_NAME' failed"
    if [[ -n "$CONTEXT" ]]; then
        echo "   $CONTEXT"
    fi
    echo ""
    echo "If this was unexpected, consider capturing it:"
    echo "  ~/.claude/skills/intent-layer/scripts/capture_mistake.sh --from-git"
    echo ""
    echo "(Ignore if exploratory/expected behavior)"
    echo ""
} >&2

exit 0
