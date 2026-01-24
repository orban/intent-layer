#!/usr/bin/env bash
# Display Intent Layer hierarchy as visual tree
# Usage: ./show_hierarchy.sh [options] [path]

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
show_hierarchy.sh - Display Intent Layer hierarchy as visual tree

USAGE:
    show_hierarchy.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    -h, --help    Show this help message
    -q, --quiet   Tree structure only (no tokens/status/age)

OUTPUT:
    ASCII tree showing:
    - Node paths with indent markers
    - Token count per node (~Xk format)
    - Validation status (✓ valid, ⚠ warning, ✗ error)
    - Staleness indicator (days since modified)

EXAMPLES:
    show_hierarchy.sh                    # Show current directory
    show_hierarchy.sh /path/to/project   # Show specific project
    show_hierarchy.sh -q .               # Tree only, no details
EOF
    exit 0
}

# Parse arguments
QUIET=false
TARGET_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -*)
            echo "❌ Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [ -n "$TARGET_PATH" ]; then
                echo "❌ Error: Multiple paths specified" >&2
                exit 1
            fi
            TARGET_PATH="$1"
            shift
            ;;
    esac
done

TARGET_PATH="${TARGET_PATH:-.}"

# Validate path exists
if [ ! -d "$TARGET_PATH" ]; then
    echo "❌ Error: Directory not found: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Please check:" >&2
    echo "     • The path is spelled correctly" >&2
    echo "     • The directory exists" >&2
    exit 1
fi

# Validate path is readable
if [ ! -r "$TARGET_PATH" ]; then
    echo "❌ Error: Permission denied reading: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Try: chmod +r \"$TARGET_PATH\"" >&2
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

# Common exclusions
EXCLUSIONS="-not -path \"*/node_modules/*\" -not -path \"*/.git/*\" -not -path \"*/dist/*\" -not -path \"*/build/*\" -not -path \"*/public/*\" -not -path \"*/target/*\" -not -path \"*/.turbo/*\" -not -path \"*/vendor/*\" -not -path \"*/.venv/*\" -not -path \"*/venv/*\" -not -path \"*/.worktrees/*\""

# Find root file
ROOT_FILE=""
if [ -f "$TARGET_PATH/CLAUDE.md" ]; then
    ROOT_FILE="CLAUDE.md"
elif [ -f "$TARGET_PATH/AGENTS.md" ]; then
    ROOT_FILE="AGENTS.md"
fi

# Collect all nodes
ALL_NODES=()

if [ -n "$ROOT_FILE" ]; then
    ALL_NODES+=("$TARGET_PATH/$ROOT_FILE")
fi

while IFS= read -r file; do
    if [ -n "$file" ] && [ "$file" != "$TARGET_PATH/AGENTS.md" ]; then
        ALL_NODES+=("$file")
    fi
done < <(eval "find \"$TARGET_PATH\" -name \"AGENTS.md\" -not -path \"$TARGET_PATH/AGENTS.md\" $EXCLUSIONS 2>/dev/null | sort" || true)

# Check if any nodes found
if [ "${#ALL_NODES[@]}" -eq 0 ]; then
    echo "=== Intent Layer Hierarchy ==="
    echo ""
    echo "(no Intent Layer nodes found)"
    echo ""
    echo "Run 'detect_state.sh' to check project state."
    exit 0
fi

get_file_age_days() {
    local file="$1"
    local mtime=""
    if mtime=$(stat -f %m "$file" 2>/dev/null); then
        : # macOS
    elif mtime=$(stat -c %Y "$file" 2>/dev/null); then
        : # Linux
    else
        echo "?"
        return
    fi
    local now=$(date +%s)
    echo $(( (now - mtime) / 86400 ))
}

format_tokens() {
    local tokens=$1
    if [ "$tokens" -ge 1000 ]; then
        echo "~$(echo "scale=1; $tokens/1000" | bc 2>/dev/null || echo "$tokens")k"
    else
        echo "~$tokens"
    fi
}

get_node_status() {
    local file="$1"
    local tokens="$2"
    local age="$3"

    # Check for errors first
    if [ "$tokens" -gt 4000 ]; then
        echo "✗"
        return
    fi

    # Check for warnings
    if [ "$tokens" -gt 3000 ]; then
        echo "⚠"
        return
    fi

    if [[ "$age" =~ ^[0-9]+$ ]] && [ "$age" -gt 90 ]; then
        echo "⚠"
        return
    fi

    echo "✓"
}

# Output header
echo "=== Intent Layer Hierarchy ==="
echo ""

# Process each node
is_first=true
for node in "${ALL_NODES[@]}"; do
    if [ ! -r "$node" ]; then
        continue
    fi

    rel_path="${node#$TARGET_PATH/}"

    # Calculate depth for indentation (count slashes)
    depth=$(echo "$rel_path" | tr -cd '/' | wc -c | tr -d ' ')

    # Build tree prefix
    prefix=""
    if [ "$is_first" = true ]; then
        # Root node - no prefix
        is_first=false
    else
        # Child nodes get tree markers
        prefix="├── "
    fi

    # Get metrics
    bytes=$(wc -c < "$node" 2>/dev/null | tr -d ' ') || bytes=0
    tokens=$((bytes / 4))
    age=$(get_file_age_days "$node")
    status=$(get_node_status "$node" "$tokens" "$age")
    tokens_fmt=$(format_tokens $tokens)

    # Output node
    echo "$prefix$rel_path"

    if [ "$QUIET" = false ]; then
        # Add details on next line with indentation
        if [ -n "$prefix" ]; then
            detail_prefix="    "
        else
            detail_prefix="    "
        fi
        echo "${detail_prefix}${tokens_fmt} tokens $status (${age}d ago)"
        echo ""
    fi
done

# Footer
if [ "$QUIET" = false ]; then
    echo "---"
    echo "Legend: ✓ valid | ⚠ warning | ✗ error"
fi
