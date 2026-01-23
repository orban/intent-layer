#!/usr/bin/env bash
# Detect stale Intent Layer nodes
# Usage: ./detect_staleness.sh [OPTIONS] [PATH]

set -euo pipefail

show_help() {
    cat << 'EOF'
detect_staleness.sh - Find Intent Layer nodes that may be stale

USAGE:
    detect_staleness.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Root directory to scan (default: current directory)

OPTIONS:
    -h, --help           Show this help message
    -t, --threshold N    Days since node update to consider stale (default: 90)
    -c, --code-changes   Also check if code changed more recently than node
    -q, --quiet          Output only stale node paths, no headers
    --json               Output as JSON (not yet implemented)

STALENESS CRITERIA:
    1. Node file older than threshold days
    2. Code in directory changed after node was last updated (with -c)
    3. High commit activity but no node updates

OUTPUT:
    Table of potentially stale nodes with reasons

EXAMPLES:
    detect_staleness.sh                      # Check all nodes, 90-day threshold
    detect_staleness.sh --threshold 30       # Stricter threshold
    detect_staleness.sh --code-changes       # Check code vs node dates
    detect_staleness.sh src/                 # Check specific subtree

EXIT CODES:
    0    No stale nodes found
    1    Error (invalid path, etc.)
    2    Stale nodes found (useful for CI)
EOF
    exit 0
}

# Defaults
TARGET_PATH="."
THRESHOLD=90
CHECK_CODE=false
QUIET=false
JSON_OUTPUT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -t|--threshold)
            THRESHOLD="$2"
            shift 2
            ;;
        -c|--code-changes)
            CHECK_CODE=true
            shift
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
    echo "⚠️  JSON output not yet implemented, using table format" >&2
    JSON_OUTPUT=false
fi

# Validate path
if [ ! -d "$TARGET_PATH" ]; then
    echo "❌ Error: Directory not found: $TARGET_PATH" >&2
    exit 1
fi

TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

# Check if git repo (needed for code-changes check)
IS_GIT_REPO=false
REPO_ROOT=""
if git -C "$TARGET_PATH" rev-parse --git-dir > /dev/null 2>&1; then
    IS_GIT_REPO=true
    REPO_ROOT=$(git -C "$TARGET_PATH" rev-parse --show-toplevel)
fi

if [ "$CHECK_CODE" = true ] && [ "$IS_GIT_REPO" = false ]; then
    echo "⚠️  Warning: --code-changes requires git repository, ignoring" >&2
    CHECK_CODE=false
fi

# Get file modification time (cross-platform)
get_mtime() {
    local file="$1"
    if stat -f %m "$file" 2>/dev/null; then
        return
    elif stat -c %Y "$file" 2>/dev/null; then
        return
    fi
    echo "0"
}

# Calculate days since modification
days_since_modified() {
    local file="$1"
    local mtime
    mtime=$(get_mtime "$file")
    local now
    now=$(date +%s)
    echo $(( (now - mtime) / 86400 ))
}

# Get most recent code change in directory (excluding .md files)
most_recent_code_change() {
    local dir="$1"

    [ "$IS_GIT_REPO" = false ] && echo "0" && return

    local rel_path="${dir#$REPO_ROOT/}"
    [ "$dir" = "$REPO_ROOT" ] && rel_path="."

    # Get most recent commit affecting non-md files in this directory
    local commit_date
    commit_date=$(git -C "$REPO_ROOT" log -1 --format="%ct" -- "$rel_path" \
        ':(exclude)*.md' ':(exclude)AGENTS.md' ':(exclude)CLAUDE.md' 2>/dev/null) || echo "0"

    echo "${commit_date:-0}"
}

# Count recent commits in directory
count_recent_commits() {
    local dir="$1"

    [ "$IS_GIT_REPO" = false ] && echo "0" && return

    local rel_path="${dir#$REPO_ROOT/}"
    [ "$dir" = "$REPO_ROOT" ] && rel_path="."

    git -C "$REPO_ROOT" rev-list --count --since="$THRESHOLD days ago" HEAD -- "$rel_path" 2>/dev/null || echo "0"
}

# Find all Intent Layer nodes
find_nodes() {
    find "$TARGET_PATH" \( -name "AGENTS.md" -o -name "CLAUDE.md" \) -type f 2>/dev/null | \
        grep -v node_modules | \
        grep -v "\.git/" | \
        grep -v "\.worktrees" || true
}

# Check staleness for a single node
check_node_staleness() {
    local node_path="$1"
    local node_dir
    node_dir=$(dirname "$node_path")

    local reasons=()
    local severity="low"

    # Check 1: Age threshold
    local days_old
    days_old=$(days_since_modified "$node_path")

    if [ "$days_old" -gt "$THRESHOLD" ]; then
        reasons+=("${days_old}d old (threshold: ${THRESHOLD}d)")
        severity="medium"
    fi

    # Check 2: Code changed more recently (if enabled)
    if [ "$CHECK_CODE" = true ]; then
        local node_mtime
        node_mtime=$(get_mtime "$node_path")
        local code_mtime
        code_mtime=$(most_recent_code_change "$node_dir")

        if [ "$code_mtime" -gt "$node_mtime" ] && [ "$code_mtime" != "0" ]; then
            local code_days_ago=$(( ($(date +%s) - code_mtime) / 86400 ))
            reasons+=("code changed ${code_days_ago}d ago")
            severity="high"
        fi
    fi

    # Check 3: High commit activity
    if [ "$IS_GIT_REPO" = true ]; then
        local recent_commits
        recent_commits=$(count_recent_commits "$node_dir")

        if [ "$recent_commits" -gt 20 ]; then
            reasons+=("${recent_commits} commits in ${THRESHOLD}d")
            [ "$severity" = "low" ] && severity="medium"
        fi
    fi

    # Output if stale
    if [ ${#reasons[@]} -gt 0 ]; then
        local reasons_str
        reasons_str=$(IFS='; '; echo "${reasons[*]}")
        echo "$severity|$node_path|$reasons_str"
    fi
}

# Collect stale nodes
declare -a STALE_NODES=()

while IFS= read -r node; do
    [ -z "$node" ] && continue
    result=$(check_node_staleness "$node")
    [ -n "$result" ] && STALE_NODES+=("$result")
done < <(find_nodes)

# Sort by severity (high first)
if [ ${#STALE_NODES[@]} -gt 0 ]; then
    IFS=$'\n' STALE_NODES=($(printf '%s\n' "${STALE_NODES[@]}" | sort -t'|' -k1 -r))
    unset IFS
fi

# Output
if [ "$QUIET" = false ]; then
    echo "## Intent Layer Staleness Report"
    echo ""
    echo "Scanned: $TARGET_PATH"
    echo "Threshold: $THRESHOLD days"
    [ "$CHECK_CODE" = true ] && echo "Code change detection: enabled"
    echo ""
fi

if [ ${#STALE_NODES[@]} -eq 0 ]; then
    if [ "$QUIET" = false ]; then
        echo "✓ No stale nodes found."
    fi
    exit 0
fi

if [ "$QUIET" = false ]; then
    echo "### Potentially Stale Nodes"
    echo ""
    echo "| Severity | Node | Reason |"
    echo "|----------|------|--------|"
fi

for entry in "${STALE_NODES[@]}"; do
    IFS='|' read -r severity path reasons <<< "$entry"
    if [ "$QUIET" = true ]; then
        echo "$path"
    else
        # Make path relative for display
        rel_path="${path#$TARGET_PATH/}"
        echo "| $severity | $rel_path | $reasons |"
    fi
done

if [ "$QUIET" = false ]; then
    echo ""
    echo "---"
    echo ""
    echo "**Recommended**: Review stale nodes and update or confirm still accurate."
    echo "Run mine_git_history.sh on affected directories to find new content."
fi

# Exit with code 2 if stale nodes found (useful for CI)
exit 2
