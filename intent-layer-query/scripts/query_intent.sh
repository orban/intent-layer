#!/usr/bin/env bash
set -euo pipefail

# query_intent.sh - Search Intent Layer for concepts and show context
#
# Usage: query_intent.sh <target_path> <search_term> [--section <section>] [--ancestors]
#
# Arguments:
#   target_path    Path to project with Intent Layer
#   search_term    Concept to search for (supports regex)
#
# Options:
#   --section <name>  Filter to specific section (e.g., "Contracts", "Pitfalls")
#   --ancestors       Include ancestor nodes in results
#   --json            Output as JSON
#   -h, --help        Show this help message
#
# Examples:
#   query_intent.sh /path/to/project "authentication"
#   query_intent.sh /path/to/project "rate.?limit" --section Contracts
#   query_intent.sh /path/to/project "session" --ancestors

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Defaults
SECTION=""
SHOW_ANCESTORS=false
OUTPUT_JSON=false

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
        --ancestors)
            SHOW_ANCESTORS=true
            shift
            ;;
        --json)
            OUTPUT_JSON=true
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
    echo "Usage: query_intent.sh <target_path> <search_term>" >&2
    exit 1
fi

TARGET_PATH="$1"
SEARCH_TERM="$2"

if [[ ! -d "$TARGET_PATH" ]]; then
    echo "Error: Directory not found: $TARGET_PATH" >&2
    exit 1
fi

# Find all Intent Nodes
find_intent_nodes() {
    find "$TARGET_PATH" \( -name "CLAUDE.md" -o -name "AGENTS.md" \) \
        -not -path "*/.git/*" \
        -not -path "*/node_modules/*" \
        -not -path "*/.claude/*" \
        2>/dev/null | sort
}

# Get parent node path for a given node
get_parent_node() {
    local node_path="$1"
    local node_dir
    node_dir=$(dirname "$node_path")

    # Walk up looking for parent Intent Node
    local current="$node_dir"
    while [[ "$current" != "$TARGET_PATH" && "$current" != "/" && "$current" != "." ]]; do
        current=$(dirname "$current")
        if [[ -f "$current/CLAUDE.md" ]]; then
            echo "$current/CLAUDE.md"
            return 0
        elif [[ -f "$current/AGENTS.md" ]]; then
            echo "$current/AGENTS.md"
            return 0
        fi
    done

    # Check root
    if [[ -f "$TARGET_PATH/CLAUDE.md" && "$node_path" != "$TARGET_PATH/CLAUDE.md" ]]; then
        echo "$TARGET_PATH/CLAUDE.md"
    elif [[ -f "$TARGET_PATH/AGENTS.md" && "$node_path" != "$TARGET_PATH/AGENTS.md" ]]; then
        echo "$TARGET_PATH/AGENTS.md"
    fi
}

# Extract section content from a file
extract_section() {
    local file="$1"
    local section="$2"

    # Match section header (## or ###)
    awk -v section="$section" '
        BEGIN { in_section = 0; level = 0 }
        /^##+ / {
            if (in_section) {
                # Check if this is same or higher level heading
                current_level = gsub(/#/, "#", $0) - gsub(/[^#]/, "", $0)
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

# Search for term in Intent Nodes
search_nodes() {
    local nodes
    nodes=$(find_intent_nodes)

    local found=false
    local results=()

    while IFS= read -r node; do
        [[ -z "$node" ]] && continue

        local rel_path="${node#$TARGET_PATH/}"
        local matches

        if [[ -n "$SECTION" ]]; then
            # Search within specific section
            matches=$(extract_section "$node" "$SECTION" | grep -in -E "$SEARCH_TERM" 2>/dev/null || true)
        else
            # Search entire file
            matches=$(grep -in -E "$SEARCH_TERM" "$node" 2>/dev/null || true)
        fi

        if [[ -n "$matches" ]]; then
            found=true

            if [[ "$OUTPUT_JSON" == "true" ]]; then
                results+=("{\"node\": \"$rel_path\", \"matches\": $(echo "$matches" | jq -R -s 'split("\n") | map(select(. != ""))')}")
            else
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "📄 $rel_path"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "$matches" | while IFS= read -r line; do
                    echo "  $line"
                done
                echo ""

                # Show ancestors if requested
                if [[ "$SHOW_ANCESTORS" == "true" ]]; then
                    local parent
                    parent=$(get_parent_node "$node")
                    if [[ -n "$parent" ]]; then
                        echo "  ↑ Parent: ${parent#$TARGET_PATH/}"
                    fi
                    echo ""
                fi
            fi
        fi
    done <<< "$nodes"

    if [[ "$OUTPUT_JSON" == "true" ]]; then
        echo "[$(IFS=,; echo "${results[*]}")]"
    elif [[ "$found" == "false" ]]; then
        echo "No matches found for '$SEARCH_TERM' in Intent Layer" >&2
        echo "" >&2
        echo "Suggestions:" >&2
        echo "  - Try a broader search term" >&2
        echo "  - Check if Intent Layer is complete: detect_state.sh $TARGET_PATH" >&2
        echo "  - This concept may not be documented yet" >&2
        exit 1
    fi
}

# Show summary header
if [[ "$OUTPUT_JSON" != "true" ]]; then
    echo ""
    echo "🔍 Searching Intent Layer for: $SEARCH_TERM"
    [[ -n "$SECTION" ]] && echo "   Section filter: $SECTION"
    echo ""
fi

search_nodes
