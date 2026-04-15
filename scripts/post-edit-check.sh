#!/usr/bin/env bash
#
# post-edit-check.sh - PostToolUse hook for Intent Layer
#
# Checks if an edited file is covered by an AGENTS.md node and outputs
# a reminder if the edit might affect documented contracts/patterns.
#
# Usage: post-edit-check.sh "<tool_input_json>"
#
# Performance target: <500ms (only flags, doesn't analyze deeply)
#
# Exit codes:
#   0 - Success (output reminder or silent if not relevant)
#   1 - Error (invalid input, etc.)

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
source "$PLUGIN_ROOT/lib/common.sh"

# Parse the file path from the PostToolUse CLI payload.
# Claude passes `tool_input` as a JSON string argument for PostToolUse.
TOOL_INPUT="${1:-}"

if [[ -z "$TOOL_INPUT" ]]; then
    exit 0  # No input, silently exit
fi

TOOL_NAME=$(json_get "$TOOL_INPUT" '.tool_name' '')
FILE_PATH=$(extract_hook_file_path "$TOOL_INPUT")

if [[ -z "$FILE_PATH" ]]; then
    exit 0  # No file path found, silently exit
fi

if [[ -z "$TOOL_NAME" ]]; then
    if echo "$TOOL_INPUT" | grep -q '"notebook_path"' 2>/dev/null; then
        TOOL_NAME="NotebookEdit"
    elif echo "$TOOL_INPUT" | grep -q '"old_string"' 2>/dev/null; then
        TOOL_NAME="Edit"
    else
        TOOL_NAME="Write"
    fi
fi

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"

FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"

# Get the directory of the edited file
FILE_DIR=$(dirname "$FILE_PATH")
FILE_NAME=$(basename "$FILE_PATH")

# Find covering node
COVERING_NODE=""
if [[ -x "$FIND_NODE" ]]; then
    COVERING_NODE=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)
fi

COVERAGE_STATUS="uncovered"
if [[ -n "$COVERING_NODE" ]]; then
    COVERAGE_STATUS="covered"
fi

# Quick relevance check based on file type/name
# Files that likely affect documented behavior
is_likely_relevant() {
    local file="$1"

    # Skip common non-relevant files
    case "$file" in
        *.md|*.txt|*.json|*.yaml|*.yml|*.lock|*.log)
            return 1
            ;;
        *.test.*|*.spec.*|*_test.*|*_spec.*)
            return 1
            ;;
    esac

    # Source files are relevant
    case "$file" in
        *.ts|*.js|*.tsx|*.jsx|*.py|*.go|*.rs|*.java|*.rb|*.sh|*.ipynb)
            return 0
            ;;
    esac

    # Config files might be relevant
    case "$file" in
        *config*|*Config*|*.env*)
            return 0
            ;;
    esac

    return 1
}

# Check relevance
REMINDER_ALLOWED=true
if ! is_likely_relevant "$FILE_NAME"; then
    REMINDER_ALLOWED=false
fi

OUTCOME_DETAIL="post-edit-check"
if [[ ! -e "$FILE_PATH" ]]; then
    OUTCOME_DETAIL="path-missing-after-write"
fi

if [[ "$COVERAGE_STATUS" == "covered" ]] && $REMINDER_ALLOWED; then
    # Calculate relative path from covering node to edited file
    NODE_DIR=$(dirname "$COVERING_NODE")
    RELATIVE_PATH="${FILE_PATH#$NODE_DIR/}"

    # Output reminder (this is what Claude sees)
    echo "ℹ️ Intent Layer: $RELATIVE_PATH is covered by $COVERING_NODE"
    echo "   Review if behavior changed: Contracts, Entry Points, Pitfalls"
fi

# --- New Directory Detection ---
# Check if this file was written to a new directory that may need AGENTS.md

# Directories that never need AGENTS.md
is_excluded_directory() {
    local dir_name="$1"
    case "$dir_name" in
        node_modules|.git|.svn|.hg|build|dist|out|target|__pycache__|.cache|\
        .next|.nuxt|.output|coverage|.nyc_output|.pytest_cache|.mypy_cache|\
        vendor|deps|_deps|packages|.packages|.pub-cache|Pods|.gradle|.idea|\
        .vscode|.github|.gitlab|.circleci|.husky|.yarn|.pnp|tmp|temp|logs)
            return 0
            ;;
        .*)
            # All dotfile directories are excluded
            return 0
            ;;
    esac
    return 1
}

# Check if directory is "new" (has very few files)
is_new_directory() {
    local dir="$1"
    local file_count
    # Count files (not directories) in this directory only
    file_count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
    [[ "$file_count" -le 2 ]]
}

# Check if parent directory has Intent Layer coverage
parent_has_coverage() {
    local dir="$1"
    local parent
    parent=$(dirname "$dir")
    [[ -f "$parent/AGENTS.md" || -f "$parent/CLAUDE.md" ]]
}

DIR_NAME=$(basename "$FILE_DIR")

# Only suggest if:
# 1. This directory doesn't have its own AGENTS.md
# 2. Directory is not excluded
# 3. Directory is "new" (≤2 files)
# 4. Parent has coverage (we're extending hierarchy, not starting fresh)
if [[ -d "$FILE_DIR" ]] && \
   [[ ! -f "$FILE_DIR/AGENTS.md" ]] && \
   ! is_excluded_directory "$DIR_NAME" && \
   is_new_directory "$FILE_DIR" && \
   parent_has_coverage "$FILE_DIR"; then
    echo ""
    echo "📁 New directory \`$DIR_NAME\` created - may need AGENTS.md coverage as it grows."
    echo "   Run \`/intent-layer-maintenance\` when ready to extend the hierarchy."
fi

append_outcome_telemetry "$PROJECT_ROOT" "$TOOL_NAME" "success" "$FILE_PATH" "$COVERAGE_STATUS" "${COVERING_NODE:-None}" "$OUTCOME_DETAIL"
