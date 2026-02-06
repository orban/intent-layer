#!/usr/bin/env bash
# Mine git history for Intent Layer insights
# Usage: ./mine_git_history.sh [OPTIONS] [PATH]

set -euo pipefail

show_help() {
    cat << 'EOF'
mine_git_history.sh - Extract Intent Layer content from git history

USAGE:
    mine_git_history.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    -h, --help           Show this help message
    -s, --since DATE     Analyze commits since DATE (default: 1 year ago)
    -d, --depth N        Limit to N most recent commits per category
    -q, --quiet          Output only findings, no headers
    --json               Output as JSON (not yet implemented; warns and uses markdown)

CATEGORIES SEARCHED:
    Bug fixes      Commits with "fix", "bug", "broken", "issue"
    Reverts        Commits with "revert", "rollback", "undo"
    Refactors      Commits with "refactor", "restructure", "reorganize"
    Breaking       Commits with "BREAKING", "migration", "breaking change"

OUTPUT:
    Markdown table of findings categorized by Intent Layer section

EXAMPLES:
    mine_git_history.sh                     # Current directory, 1 year
    mine_git_history.sh src/api/            # Specific directory
    mine_git_history.sh --since "6 months ago" .
    mine_git_history.sh --depth 10 src/     # Limit to 10 per category

EXIT CODES:
    0    Success (findings may be empty)
    1    Error (invalid path, not a git repo)
EOF
    exit 0
}

# Defaults
TARGET_PATH="."
SINCE="1 year ago"
DEPTH=""
QUIET=false
JSON_OUTPUT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -s|--since)
            SINCE="$2"
            shift 2
            ;;
        -d|--depth)
            DEPTH="$2"
            shift 2
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        -*)
            echo "❌ Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            TARGET_PATH="$1"
            shift
            ;;
    esac
done

# TODO: JSON output not yet implemented
if [ "$JSON_OUTPUT" = true ]; then
    echo "⚠️  JSON output not yet implemented, using markdown" >&2
    JSON_OUTPUT=false
fi

# Validate path
if [ ! -d "$TARGET_PATH" ]; then
    echo "❌ Error: Directory not found: $TARGET_PATH" >&2
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

# Check if git repo
if ! git -C "$TARGET_PATH" rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: Not a git repository: $TARGET_PATH" >&2
    echo "" >&2
    echo "   This script requires a git repository to analyze history." >&2
    exit 1
fi

# Get relative path from repo root for git log
REPO_ROOT=$(git -C "$TARGET_PATH" rev-parse --show-toplevel)
if [ "$TARGET_PATH" = "$REPO_ROOT" ]; then
    REL_PATH=""
else
    REL_PATH="${TARGET_PATH#$REPO_ROOT/}"
fi

DIR_NAME=$(basename "$TARGET_PATH")

# Search for commits matching pattern
search_commits() {
    local pattern="$1"
    local depth_args=()
    local path_args=()

    [ -n "$DEPTH" ] && depth_args+=("-n" "$DEPTH")
    [ -n "$REL_PATH" ] && path_args=("--" "$REL_PATH")

    git -C "$REPO_ROOT" log \
        --since="$SINCE" \
        --grep="$pattern" -i \
        --pretty=format:"%h|%s" \
        "${depth_args[@]+"${depth_args[@]}"}" \
        "${path_args[@]+"${path_args[@]}"}" 2>/dev/null || true
}

# Extract findings for a category
extract_category() {
    local pattern="$1"
    local section="$2"

    local commits
    commits=$(search_commits "$pattern")

    if [ -z "$commits" ]; then
        return
    fi

    echo "$commits" | while IFS='|' read -r hash subject; do
        [ -z "$hash" ] && continue
        echo "$hash|$subject|$section"
    done
}

# Output markdown table
output_markdown() {
    local title="$1"
    shift
    local findings=("$@")

    if [ ${#findings[@]} -eq 0 ]; then
        return
    fi

    echo ""
    echo "### $title"
    echo ""
    echo "| Commit | Finding | Confidence |"
    echo "|--------|---------|------------|"

    for finding in "${findings[@]}"; do
        IFS='|' read -r hash subject section <<< "$finding"
        # Escape pipes in subject
        subject="${subject//|/\\|}"
        echo "| $hash | $subject | Medium |"
    done
}

# Collect all findings
declare -a PITFALLS=()
declare -a ANTIPATTERNS=()
declare -a DECISIONS=()
declare -a CONTRACTS=()

# Search each category
while IFS= read -r line; do
    [ -n "$line" ] && PITFALLS+=("$line")
done < <(extract_category "fix\|bug\|broken\|issue" "Pitfalls")

while IFS= read -r line; do
    [ -n "$line" ] && ANTIPATTERNS+=("$line")
done < <(extract_category "revert\|rollback\|undo" "Anti-patterns")

while IFS= read -r line; do
    [ -n "$line" ] && DECISIONS+=("$line")
done < <(extract_category "refactor\|restructure\|reorganize" "Architecture Decisions")

while IFS= read -r line; do
    [ -n "$line" ] && CONTRACTS+=("$line")
done < <(extract_category "BREAKING\|migration\|breaking change" "Contracts")

# Output results
if [ "$QUIET" = false ]; then
    echo "## Git History Findings for $DIR_NAME"
    echo ""
    echo "Analyzed commits since: $SINCE"
    [ -n "$REL_PATH" ] && echo "Path: $REL_PATH"
    echo ""
fi

total_findings=$((${#PITFALLS[@]} + ${#ANTIPATTERNS[@]} + ${#DECISIONS[@]} + ${#CONTRACTS[@]}))

if [ "$total_findings" -eq 0 ]; then
    if [ "$QUIET" = false ]; then
        echo "No findings from git history."
        echo ""
        echo "This could mean:"
        echo "- Commit messages don't use conventional keywords"
        echo "- No relevant commits in the time range"
        echo "- Try extending --since or checking PR descriptions instead"
    fi
    exit 0
fi

output_markdown "Potential Pitfalls (from bug fixes)" "${PITFALLS[@]+"${PITFALLS[@]}"}"
output_markdown "Potential Anti-patterns (from reverts)" "${ANTIPATTERNS[@]+"${ANTIPATTERNS[@]}"}"
output_markdown "Potential Architecture Decisions (from refactors)" "${DECISIONS[@]+"${DECISIONS[@]}"}"
output_markdown "Potential Contracts (from breaking changes)" "${CONTRACTS[@]+"${CONTRACTS[@]}"}"

echo ""
echo "---"
echo ""
echo "**Review needed**: Human should verify findings before adding to AGENTS.md."
echo "Total findings: $total_findings"
