#!/usr/bin/env bash
set -euo pipefail

# walk_ancestors.sh - Walk from a node to root, collecting context from ancestors
#
# Usage: walk_ancestors.sh <target_path> <start_path> [--section <section>]
#
# Arguments:
#   target_path    Path to project root with Intent Layer
#   start_path     Starting node or directory to walk up from
#
# Options:
#   --section <name>  Only show specific section from each node
#   --tldrs           Only show TL;DR from each node
#   --contracts       Only show Contracts section from each node
#   --pitfalls        Only show Pitfalls section from each node
#   -h, --help        Show this help message
#
# Examples:
#   walk_ancestors.sh /project src/api/routes/
#   walk_ancestors.sh /project src/api/AGENTS.md --contracts
#   walk_ancestors.sh /project src/auth/ --section "Entry Points"

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Defaults
SECTION=""
SHOW_TLDRS=false
SHOW_CONTRACTS=false
SHOW_PITFALLS=false

# Parse arguments
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        --section)
            SECTION="$2"
            shift 2
            ;;
        --tldrs)
            SHOW_TLDRS=true
            shift
            ;;
        --contracts)
            SHOW_CONTRACTS=true
            SECTION="Contracts"
            shift
            ;;
        --pitfalls)
            SHOW_PITFALLS=true
            SECTION="Pitfalls"
            shift
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [[ $# -lt 2 ]]; then
    echo "Error: Missing required arguments" >&2
    echo "Usage: walk_ancestors.sh <target_path> <start_path>" >&2
    exit 1
fi

TARGET_PATH="$1"
START_PATH="$2"

# Normalize paths
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)
if [[ -d "$START_PATH" ]]; then
    START_PATH=$(cd "$START_PATH" && pwd)
elif [[ -f "$START_PATH" ]]; then
    START_PATH=$(cd "$(dirname "$START_PATH")" && pwd)
else
    echo "Error: Path not found: $START_PATH" >&2
    exit 1
fi

# Extract TL;DR from a file
extract_tldr() {
    local file="$1"
    # Look for > **TL;DR**: or > TL;DR: patterns
    grep -m1 -E "^>.*TL;DR" "$file" 2>/dev/null | sed 's/^> *//' || true
}

# Extract section content from a file
extract_section() {
    local file="$1"
    local section="$2"

    awk -v section="$section" '
        BEGIN { in_section = 0; level = 0 }
        /^##+ / {
            if (in_section) {
                match($0, /^#+/)
                current_level = RLENGTH
                if (current_level <= level) {
                    in_section = 0
                }
            }
            if (tolower($0) ~ tolower(section)) {
                in_section = 1
                match($0, /^#+/)
                level = RLENGTH
            }
        }
        in_section { print }
    ' "$file"
}

# Find Intent Node in a directory
find_node_in_dir() {
    local dir="$1"
    if [[ -f "$dir/AGENTS.md" ]]; then
        echo "$dir/AGENTS.md"
    elif [[ -f "$dir/CLAUDE.md" ]]; then
        echo "$dir/CLAUDE.md"
    fi
}

# Collect all ancestor nodes from start to root
collect_ancestors() {
    local current="$START_PATH"
    local nodes=()

    # First, find the most specific node at or below current
    local node
    node=$(find_node_in_dir "$current")
    [[ -n "$node" ]] && nodes+=("$node")

    # Walk up to root
    while [[ "$current" != "$TARGET_PATH" && "$current" != "/" ]]; do
        current=$(dirname "$current")
        node=$(find_node_in_dir "$current")
        if [[ -n "$node" ]]; then
            # Avoid duplicates
            local already_added=false
            for n in "${nodes[@]:-}"; do
                [[ "$n" == "$node" ]] && already_added=true
            done
            [[ "$already_added" == "false" ]] && nodes+=("$node")
        fi
    done

    # Output nodes (most specific first)
    printf '%s\n' "${nodes[@]:-}"
}

# Display a node
display_node() {
    local node="$1"
    local depth="$2"
    local rel_path="${node#$TARGET_PATH/}"

    local indent=""
    for ((i=0; i<depth; i++)); do
        indent="  $indent"
    done

    echo "${indent}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ $depth -eq 0 ]]; then
        echo "${indent}📍 $rel_path (starting node)"
    else
        echo "${indent}↑ $rel_path"
    fi
    echo "${indent}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [[ "$SHOW_TLDRS" == "true" ]]; then
        local tldr
        tldr=$(extract_tldr "$node")
        if [[ -n "$tldr" ]]; then
            echo "${indent}$tldr"
        else
            echo "${indent}(no TL;DR found)"
        fi
    elif [[ -n "$SECTION" ]]; then
        local content
        content=$(extract_section "$node" "$SECTION")
        if [[ -n "$content" ]]; then
            echo "$content" | while IFS= read -r line; do
                echo "${indent}$line"
            done
        else
            echo "${indent}(section '$SECTION' not found)"
        fi
    else
        # Show full content (truncated)
        head -50 "$node" | while IFS= read -r line; do
            echo "${indent}$line"
        done
        local total_lines
        total_lines=$(wc -l < "$node" | tr -d ' ')
        if [[ $total_lines -gt 50 ]]; then
            echo "${indent}... ($((total_lines - 50)) more lines)"
        fi
    fi

    echo ""
}

# Main
echo ""
echo "🚶 Walking ancestors from: ${START_PATH#$TARGET_PATH/}"
echo "   Project root: $TARGET_PATH"
[[ -n "$SECTION" ]] && echo "   Section filter: $SECTION"
echo ""

nodes=$(collect_ancestors)

if [[ -z "$nodes" ]]; then
    echo "No Intent Nodes found in ancestor path" >&2
    echo "" >&2
    echo "The path $START_PATH has no CLAUDE.md or AGENTS.md files in its ancestry." >&2
    exit 1
fi

depth=0
while IFS= read -r node; do
    [[ -z "$node" ]] && continue
    display_node "$node" "$depth"
    ((depth++))
done <<< "$nodes"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Found $depth ancestor node(s)"
echo ""
