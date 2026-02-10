#!/usr/bin/env bash
# PostToolUseFailure hook - Auto-captures mistakes on significant tool failures
# Input: JSON on stdin with tool_name, tool_input, etc.
# Output: additionalContext JSON to stdout (skeleton report created)
#
# Creates skeleton reports in .intent-layer/mistakes/pending/
# These are enriched by the Stop hook at session end

set -euo pipefail

# Source shared library
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
source "$PLUGIN_ROOT/lib/common.sh"

# Read hook input
INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# Extract fields
TOOL_NAME=$(json_get "$INPUT" '.tool_name' 'unknown')
FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
FILE_PATH=${FILE_PATH:-$(json_get "$INPUT" '.tool_input.notebook_path' '')}
COMMAND=$(json_get "$INPUT" '.tool_input.command' '')
OLD_STRING=$(json_get "$INPUT" '.tool_input.old_string' '')
NEW_STRING=$(json_get "$INPUT" '.tool_input.new_string' '')

# Skip expected/exploratory failures
case "$TOOL_NAME" in
    Read|Glob|Grep|LS)
        # File exploration failures are expected - silent exit
        exit 0
        ;;
    Bash)
        # Skip common exploratory bash failures unless file-modifying
        if [[ -z "$FILE_PATH" ]]; then
            exit 0
        fi
        ;;
esac

# Determine project root
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"

# Create skeleton report directory
SKELETON_DIR="$PROJECT_ROOT/.intent-layer/mistakes/pending"
mkdir -p "$SKELETON_DIR"

# Generate report ID
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PART=$(date +"%Y-%m-%d")
REPORT_ID="SKELETON-$DATE_PART-$(printf '%04d' $((RANDOM % 10000)))"
REPORT_FILE="$SKELETON_DIR/$REPORT_ID.md"

# Determine directory context
if [[ -n "$FILE_PATH" ]]; then
    TARGET_DIR=$(dirname "$FILE_PATH")
else
    TARGET_DIR="unknown"
fi

# Find covering node if possible
FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"
COVERING_NODE="None"
if [[ -x "$FIND_NODE" && -n "$FILE_PATH" ]]; then
    COVERING_NODE=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || echo "None")
fi

# Build operation description from available context
OPERATION="$TOOL_NAME operation"
if [[ -n "$FILE_PATH" ]]; then
    OPERATION="$TOOL_NAME on $(basename "$FILE_PATH")"
fi

# Build context details
CONTEXT_DETAILS=""
if [[ -n "$FILE_PATH" ]]; then
    CONTEXT_DETAILS+="- **File**: \`$FILE_PATH\`"$'\n'
fi
if [[ -n "$COMMAND" ]]; then
    CONTEXT_DETAILS+="- **Command**: \`${COMMAND:0:100}\`"$'\n'
fi
if [[ -n "$OLD_STRING" ]]; then
    CONTEXT_DETAILS+="- **Old string** (attempted match): \`${OLD_STRING:0:50}...\`"$'\n'
fi

# Write skeleton report
cat > "$REPORT_FILE" << EOF
## Learning Report (Skeleton)

**ID**: $REPORT_ID
**Type**: pitfall
**Timestamp**: $TIMESTAMP
**Directory**: $TARGET_DIR
**Operation**: $OPERATION
**Status**: skeleton (awaiting enrichment)

### What Went Wrong
<!-- Auto-captured: Tool failure detected -->
Tool \`$TOOL_NAME\` failed during operation.

$CONTEXT_DETAILS
### How Discovered
- [x] Agent self-caught (automatic capture)

### Why This Matters
<!-- To be filled by Stop hook or human review -->
_Awaiting analysis_

### Intent Layer Gap
- **Covering node**: $COVERING_NODE
- **Missing content**: _Awaiting analysis_

### Suggested Pitfall Entry
<!-- To be filled by Stop hook or human review -->
_Awaiting analysis_

### Disposition
<!-- Filled during review -->
- [ ] Added to AGENTS.md (section: ________)
- [ ] Rejected (reason: _______)
- [ ] Deferred (reason: _______)
- [ ] Discarded (exploratory failure, not a real learning)
EOF

# Check if this file had recent AGENTS.md injections
INJECTION_LOG="$PROJECT_ROOT/.intent-layer/hooks/injections.log"
INJECTED_CONTEXT=""
if [[ -f "$INJECTION_LOG" && -n "$FILE_PATH" ]]; then
    RECENT=$(grep "$FILE_PATH" "$INJECTION_LOG" 2>/dev/null | tail -3 || true)
    if [[ -n "$RECENT" ]]; then
        INJECTED_CONTEXT="
**Injection history**: Entries from covering AGENTS.md were injected before this edit.
Recent injections:
\`\`\`
$RECENT
\`\`\`
This failure occurred despite active AGENTS.md guidance — the entries may need improvement."
        # Append injection context to skeleton report
        {
            echo ""
            echo "$INJECTED_CONTEXT"
        } >> "$REPORT_FILE"
    fi
fi

# Output context to inform agent
CONTEXT="## Intent Layer: Mistake Captured

A skeleton mistake report was auto-created:
\`$REPORT_FILE\`

**Tool**: $TOOL_NAME
**File**: ${FILE_PATH:-N/A}

If this failure reveals a non-obvious gotcha, the Stop hook will prompt you to enrich this report at session end. If it was just exploratory (expected failure), you can ignore it or delete the skeleton.
$INJECTED_CONTEXT"

output_context "PostToolUseFailure" "$CONTEXT"
