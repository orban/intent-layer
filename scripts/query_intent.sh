#!/usr/bin/env bash
set -euo pipefail

# query_intent.sh - Search Intent Layer for concepts and show context
#
# Usage: query_intent.sh <target_path> <search_term> [options]
#
# Arguments:
#   target_path    Path to project with Intent Layer
#   search_term    Concept to search for (supports regex)
#
# Options:
#   --section <name>  Filter to specific section (e.g., "Contracts", "Pitfalls")
#   --ancestors       Include ancestor nodes in results
#   --json            Output as JSON
#   -e, --expand      Expand query with synonyms for semantic matching
#   -s, --smart       Smart section targeting based on query type
#   -h, --help        Show this help message
#
# Semantic Search (--expand):
#   Loads synonyms from references/query-synonyms.txt to find related terms.
#   Results show [EXPLICIT] for exact matches, [INFERRED] for synonym matches.
#
# Smart Search (--smart):
#   Automatically targets sections based on query prefix:
#     "how to..."  → Patterns, Entry Points
#     "what is..." → Purpose, Contracts
#     "why..."     → Design Rationale, Purpose
#     "avoid..."   → Pitfalls, Contracts
#
# Examples:
#   query_intent.sh /path/to/project "authentication"
#   query_intent.sh /path/to/project "rate.?limit" --section Contracts
#   query_intent.sh /path/to/project "session" --ancestors
#   query_intent.sh /path/to/project "error handling" --expand
#   query_intent.sh /path/to/project "how to validate" --smart

show_help() {
    # Extract and display help sections from header comments
    # Skip shebang and set -euo pipefail, then show all comment lines until first non-comment
    awk '
        NR > 2 && /^#/ {
            line = $0
            sub(/^# ?/, "", line)
            print line
        }
        NR > 2 && /^[^#]/ && !/^$/ { exit }
    ' "$0"
    exit 0
}

# Defaults
SECTION=""
SHOW_ANCESTORS=false
OUTPUT_JSON=false
EXPAND_SYNONYMS=false
SMART_SEARCH=false

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
        -e|--expand)
            EXPAND_SYNONYMS=true
            shift
            ;;
        -s|--smart)
            SMART_SEARCH=true
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

# JSON output requires jq
if [[ "$OUTPUT_JSON" == "true" ]] && ! command -v jq &>/dev/null; then
    echo "Warning: --json requires jq; falling back to plain text output." >&2
    OUTPUT_JSON=false
fi

# Determine synonyms file location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNONYMS_FILE="${SCRIPT_DIR}/../references/query-synonyms.txt"

# Load synonyms from file
declare -A SYNONYMS
load_synonyms() {
    if [[ ! -f "$SYNONYMS_FILE" ]]; then
        return 1
    fi

    while IFS= read -r line; do
        # Skip comments and blank lines
        [[ -z "$line" || "$line" =~ ^# ]] && continue

        # Parse term:synonym1,synonym2,...
        if [[ "$line" =~ ^([^:]+):(.+)$ ]]; then
            local term="${BASH_REMATCH[1]}"
            local syns="${BASH_REMATCH[2]}"
            SYNONYMS["$term"]="$syns"
        fi
    done < "$SYNONYMS_FILE"

    return 0
}

# Expand a search term with synonyms
# Returns: array of terms (original + synonyms)
expand_term() {
    local term="$1"
    local lower_term
    lower_term=$(echo "$term" | tr '[:upper:]' '[:lower:]')

    local expansions=()
    expansions+=("$term")

    # Check if this term has direct synonyms
    if [[ -n "${SYNONYMS[$lower_term]:-}" ]]; then
        IFS=',' read -ra syns <<< "${SYNONYMS[$lower_term]}"
        for syn in "${syns[@]}"; do
            expansions+=("$syn")
        done
    fi

    # Also check if this term appears as a synonym of another term
    for key in "${!SYNONYMS[@]}"; do
        if [[ "$key" != "$lower_term" && "${SYNONYMS[$key]}" =~ (^|,)"$lower_term"(,|$) ]]; then
            expansions+=("$key")
        fi
    done

    # Return unique terms
    printf '%s\n' "${expansions[@]}" | sort -u
}

# Build regex pattern from search term (with optional expansion)
build_search_pattern() {
    local term="$1"
    local expand="$2"

    if [[ "$expand" != "true" ]]; then
        echo "$term"
        return
    fi

    # Split term into words and expand each
    local words=()
    read -ra words <<< "$term"

    local patterns=()
    for word in "${words[@]}"; do
        local expanded
        expanded=$(expand_term "$word")

        # Create alternation pattern for this word
        local word_pattern
        word_pattern=$(echo "$expanded" | tr '\n' '|' | sed 's/|$//')
        patterns+=("($word_pattern)")
    done

    # Join patterns - match any expanded word
    local final_pattern
    final_pattern=$(IFS='|'; echo "${patterns[*]}")
    echo "$final_pattern"
}

# Determine confidence level of a match
get_confidence() {
    local matched_line="$1"
    local original_term="$2"

    # Check if the original term appears in the line (case insensitive)
    if echo "$matched_line" | grep -qi "$original_term"; then
        echo "EXPLICIT"
    else
        echo "INFERRED"
    fi
}

# Detect smart section targets based on query prefix
detect_smart_sections() {
    local query="$1"
    local lower_query
    lower_query=$(echo "$query" | tr '[:upper:]' '[:lower:]')

    # Pattern matching for query types
    if [[ "$lower_query" =~ ^how\ (to|do|can|should) ]]; then
        echo "Patterns,Entry Points,Quick Start"
    elif [[ "$lower_query" =~ ^what\ (is|are|does) ]]; then
        echo "Purpose,Overview,Contracts"
    elif [[ "$lower_query" =~ ^why ]]; then
        echo "Design Rationale,Purpose,Architecture"
    elif [[ "$lower_query" =~ ^avoid|^don\'t|^never|^warning ]]; then
        echo "Pitfalls,Contracts,Warnings"
    elif [[ "$lower_query" =~ ^where ]]; then
        echo "Entry Points,Architecture,Structure"
    elif [[ "$lower_query" =~ ^when ]]; then
        echo "Contracts,Patterns,Guidelines"
    else
        # Default: no section filtering
        echo ""
    fi
}

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

# Extract content from multiple sections
extract_sections() {
    local file="$1"
    local sections="$2"  # comma-separated list

    IFS=',' read -ra section_list <<< "$sections"
    for section in "${section_list[@]}"; do
        extract_section "$file" "$section"
    done
}

# List directories with AGENTS.md (for no-results suggestions)
list_covered_areas() {
    local nodes
    nodes=$(find_intent_nodes)

    echo "Covered areas in Intent Layer:"
    while IFS= read -r node; do
        [[ -z "$node" ]] && continue
        local dir
        dir=$(dirname "$node")
        local rel_dir="${dir#$TARGET_PATH/}"
        [[ "$rel_dir" == "$dir" ]] && rel_dir="(root)"
        echo "  - $rel_dir"
    done <<< "$nodes" | head -10

    local count
    count=$(echo "$nodes" | wc -l | tr -d ' ')
    if [[ "$count" -gt 10 ]]; then
        echo "  ... and $((count - 10)) more"
    fi
}

# Search for term in Intent Nodes
search_nodes() {
    local nodes
    nodes=$(find_intent_nodes)

    # Build search pattern
    local search_pattern
    search_pattern=$(build_search_pattern "$SEARCH_TERM" "$EXPAND_SYNONYMS")

    # Handle smart section targeting
    local smart_sections=""
    if [[ "$SMART_SEARCH" == "true" && -z "$SECTION" ]]; then
        smart_sections=$(detect_smart_sections "$SEARCH_TERM")
        if [[ -n "$smart_sections" && "$OUTPUT_JSON" != "true" ]]; then
            echo "   Smart targeting sections: $smart_sections"
            echo ""
        fi
    fi

    local found=false
    local results=()

    while IFS= read -r node; do
        [[ -z "$node" ]] && continue

        local rel_path="${node#$TARGET_PATH/}"
        local matches
        local content

        # Determine what content to search
        if [[ -n "$SECTION" ]]; then
            # User-specified section filter
            content=$(extract_section "$node" "$SECTION")
        elif [[ -n "$smart_sections" ]]; then
            # Smart search section targeting
            content=$(extract_sections "$node" "$smart_sections")
        else
            # Search entire file
            content=$(cat "$node")
        fi

        # Search content
        matches=$(echo "$content" | grep -in -E "$search_pattern" 2>/dev/null || true)

        if [[ -n "$matches" ]]; then
            found=true

            if [[ "$OUTPUT_JSON" == "true" ]]; then
                results+=("{\"node\": \"$rel_path\", \"matches\": $(echo "$matches" | jq -R -s 'split("\n") | map(select(. != ""))')}")
            else
                echo "----------------------------------------------------------------"
                echo "  $rel_path"
                echo "----------------------------------------------------------------"

                # Process each match line
                echo "$matches" | while IFS= read -r line; do
                    if [[ "$EXPAND_SYNONYMS" == "true" ]]; then
                        local confidence
                        confidence=$(get_confidence "$line" "$SEARCH_TERM")
                        echo "  [$confidence] $line"
                    else
                        echo "  $line"
                    fi
                done
                echo ""

                # Show ancestors if requested
                if [[ "$SHOW_ANCESTORS" == "true" ]]; then
                    local parent
                    parent=$(get_parent_node "$node")
                    if [[ -n "$parent" ]]; then
                        echo "  ^ Parent: ${parent#$TARGET_PATH/}"
                    fi
                    echo ""
                fi
            fi
        fi
    done <<< "$nodes"

    if [[ "$OUTPUT_JSON" == "true" ]]; then
        echo "[$(IFS=,; echo "${results[*]}")]"
    elif [[ "$found" == "false" ]]; then
        echo "" >&2
        echo "No documentation found for: '$SEARCH_TERM'" >&2
        echo "" >&2

        # Provide helpful suggestions
        echo "Suggestions:" >&2
        if [[ "$EXPAND_SYNONYMS" != "true" ]]; then
            echo "  - Try: --expand to search synonyms" >&2
        fi
        if [[ "$SMART_SEARCH" != "true" ]]; then
            echo "  - Try: --smart for section-aware search" >&2
        fi
        echo "  - Try a broader search term or different phrasing" >&2
        echo "  - Check if Intent Layer is complete: detect_state.sh $TARGET_PATH" >&2
        echo "" >&2

        # Show covered areas
        list_covered_areas >&2
        exit 1
    fi
}

# Load synonyms if expansion is enabled
if [[ "$EXPAND_SYNONYMS" == "true" ]]; then
    if ! load_synonyms; then
        echo "Warning: Could not load synonyms file: $SYNONYMS_FILE" >&2
        echo "         Falling back to exact search." >&2
        EXPAND_SYNONYMS=false
    fi
fi

# Show summary header
if [[ "$OUTPUT_JSON" != "true" ]]; then
    echo ""
    echo "Searching Intent Layer for: $SEARCH_TERM"
    [[ -n "$SECTION" ]] && echo "   Section filter: $SECTION"
    [[ "$EXPAND_SYNONYMS" == "true" ]] && echo "   Synonym expansion: enabled"
    [[ "$SMART_SEARCH" == "true" ]] && echo "   Smart targeting: enabled"
    echo ""
fi

search_nodes
