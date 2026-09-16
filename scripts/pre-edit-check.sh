#!/usr/bin/env bash
# PreToolUse hook for Edit/Write - Injects learnings via additionalContext
# Input: JSON on stdin with tool_name, tool_input
# Output: JSON with additionalContext to stdout
#
# Injects actionable sections from covering AGENTS.md:
#   - Rules: Imperative constraints from git history, failure modes
#   - Contracts: Invariants not enforced by the type system
#   - Boundaries: Import/dependency constraints, isolation rules

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

# Extract a section from the node file
# Usage: extract_section "Section Name"
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

# Extract actionable sections from the covering node
RULES=""
CONTRACTS=""
BOUNDARIES=""

if [[ -n "$NODE_PATH" && -r "$NODE_PATH" ]]; then
    RULES=$(extract_section "Rules")
    CONTRACTS=$(extract_section "Contracts")
    BOUNDARIES=$(extract_section "Boundaries")
fi

# Exit if no actionable sections found
if [[ -z "$RULES" && -z "$CONTRACTS" && -z "$BOUNDARIES" ]]; then
    exit 0
fi

# Build context message with all non-empty sections
LEARNINGS=""

for section_content in "$BOUNDARIES" "$CONTRACTS" "$RULES"; do
    if [[ -n "$section_content" ]]; then
        if [[ -n "$LEARNINGS" ]]; then
            LEARNINGS="$LEARNINGS

$section_content"
        else
            LEARNINGS="$section_content"
        fi
    fi
done

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

# Injection audit log (feedback data trail)
LOG_DIR="${CLAUDE_PROJECT_DIR:-.}/.intent-layer/hooks"
if [[ -d "${CLAUDE_PROJECT_DIR:-.}/.intent-layer" ]]; then
    mkdir -p "$LOG_DIR"
    INJECTED_SECTIONS=""
    [[ -n "$RULES" ]] && INJECTED_SECTIONS="${INJECTED_SECTIONS}Rules,"
    [[ -n "$CONTRACTS" ]] && INJECTED_SECTIONS="${INJECTED_SECTIONS}Contracts,"
    [[ -n "$BOUNDARIES" ]] && INJECTED_SECTIONS="${INJECTED_SECTIONS}Boundaries,"
    INJECTED_SECTIONS="${INJECTED_SECTIONS%,}"  # trim trailing comma
    printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$FILE_PATH" "$NODE_PATH" "$INJECTED_SECTIONS" \
        >> "$LOG_DIR/injections.log" 2>/dev/null || true
    # Rotate log when it exceeds 1000 lines to stay within hook latency budget
    LOG_LINES=$(wc -l < "$LOG_DIR/injections.log" 2>/dev/null || echo 0)
    if [[ "${LOG_LINES// /}" -gt 1000 ]]; then
        tail -500 "$LOG_DIR/injections.log" > "$LOG_DIR/injections.log.tmp" && \
            mv "$LOG_DIR/injections.log.tmp" "$LOG_DIR/injections.log"
    fi
fi
