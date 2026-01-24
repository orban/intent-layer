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

# Parse the file path from tool input JSON
# Expected format: {"file_path": "/path/to/file", ...}
TOOL_INPUT="${1:-}"

if [[ -z "$TOOL_INPUT" ]]; then
    exit 0  # No input, silently exit
fi

# Extract file_path from JSON (simple extraction, avoids jq dependency)
# Use POSIX character classes for cross-platform compatibility
FILE_PATH=$(echo "$TOOL_INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' || true)

if [[ -z "$FILE_PATH" ]]; then
    exit 0  # No file path found, silently exit
fi

# Check if file exists
if [[ ! -f "$FILE_PATH" ]]; then
    exit 0  # File doesn't exist (maybe being created), skip
fi

# Find covering AGENTS.md by walking up the directory tree
find_covering_node() {
    local dir="$1"
    local max_depth=20  # Prevent infinite loops
    local depth=0

    while [[ "$dir" != "/" && $depth -lt $max_depth ]]; do
        # Check for AGENTS.md in this directory
        if [[ -f "$dir/AGENTS.md" ]]; then
            echo "$dir/AGENTS.md"
            return 0
        fi
        # Also check for CLAUDE.md at root level
        if [[ -f "$dir/CLAUDE.md" && ! -f "$dir/../CLAUDE.md" ]]; then
            echo "$dir/CLAUDE.md"
            return 0
        fi
        dir=$(dirname "$dir")
        ((depth++))
    done

    return 1  # No covering node found
}

# Get the directory of the edited file
FILE_DIR=$(dirname "$FILE_PATH")
FILE_NAME=$(basename "$FILE_PATH")

# Find covering node
COVERING_NODE=$(find_covering_node "$FILE_DIR") || exit 0

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
        *.ts|*.js|*.tsx|*.jsx|*.py|*.go|*.rs|*.java|*.rb|*.sh)
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
if ! is_likely_relevant "$FILE_NAME"; then
    exit 0  # Not relevant, silent exit
fi

# Calculate relative path from covering node to edited file
NODE_DIR=$(dirname "$COVERING_NODE")
RELATIVE_PATH="${FILE_PATH#$NODE_DIR/}"

# Output reminder (this is what Claude sees)
echo "ℹ️ Intent Layer: $RELATIVE_PATH is covered by $COVERING_NODE"
echo "   Review if behavior changed: Contracts, Entry Points, Pitfalls"

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
if [[ ! -f "$FILE_DIR/AGENTS.md" ]] && \
   ! is_excluded_directory "$DIR_NAME" && \
   is_new_directory "$FILE_DIR" && \
   parent_has_coverage "$FILE_DIR"; then
    echo ""
    echo "📁 New directory \`$DIR_NAME\` created - may need AGENTS.md coverage as it grows."
    echo "   Run \`/intent-layer-maintenance\` when ready to extend the hierarchy."
fi
