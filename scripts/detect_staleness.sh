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
    --entries            Check individual entries for stale references
    --entries-quick      Quick mode: only check file paths, skip function names
    --json               Output as JSON (not yet implemented)

STALENESS CRITERIA:
    1. Node file older than threshold days
    2. Code in directory changed after node was last updated (with -c)
    3. High commit activity but no node updates

ENTRY-LEVEL STALENESS (with --entries):
    For each entry in Pitfalls, Contracts, Entry Points, etc.:
    - Check if referenced file paths still exist
    - Check if backticked identifiers (functions, classes) exist in code
    - Report specific entries with broken references

OUTPUT:
    Table of potentially stale nodes with reasons
    With --entries: detailed entry-level staleness report

INTEGRATION:
    audit_intent_layer.sh can use node-level staleness directly.
    For deeper checks, run detect_staleness.sh --entries separately.

EXAMPLES:
    detect_staleness.sh                      # Check all nodes, 90-day threshold
    detect_staleness.sh --threshold 30       # Stricter threshold
    detect_staleness.sh --code-changes       # Check code vs node dates
    detect_staleness.sh --entries            # Check entry references
    detect_staleness.sh --entries-quick      # Quick file-path-only check
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
CHECK_ENTRIES=false
ENTRIES_QUICK=false

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
        --entries)
            CHECK_ENTRIES=true
            shift
            ;;
        --entries-quick)
            CHECK_ENTRIES=true
            ENTRIES_QUICK=true
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

# ============================================================================
# Entry-level staleness detection functions
# ============================================================================

# Known sections that contain code references
REFERENCE_SECTIONS="Pitfalls|Contracts|Entry Points|Patterns|Code Map|Public API|External Dependencies|Data Flow|Architecture"

# Extract a section's content from a markdown file
# Usage: extract_section <file> <section_name>
extract_section() {
    local file="$1"
    local section="$2"

    # Match section header (## Section or ### Section) and capture until next section
    awk -v section="$section" '
        BEGIN { in_section = 0; IGNORECASE = 1 }
        /^##+ / {
            if (in_section) exit
            if ($0 ~ section) { in_section = 1; next }
        }
        in_section { print }
    ' "$file"
}

# Extract file references from text
# Patterns: src/api/handler.ts, lib/utils.py, ./config.json, etc.
# Must have a recognizable source code extension
extract_file_refs() {
    local text="$1"
    # Common source code and config file extensions
    # Match: path/to/file.ext or `path/to/file.ext`
    # Require: at least one directory separator OR start with ./ OR recognizable filename pattern
    echo "$text" | grep -oE '`[a-zA-Z0-9_./-]+\.(ts|js|py|go|rs|java|rb|sh|yaml|yml|json|toml|tsx|jsx|css|scss|html|sql|c|cpp|h|hpp|swift|kt|vue|svelte)`|[a-zA-Z_][a-zA-Z0-9_]*(/[a-zA-Z0-9_.-]+)+\.(ts|js|py|go|rs|java|rb|sh|yaml|yml|json|toml|tsx|jsx|css|scss|html|sql|c|cpp|h|hpp|swift|kt|vue|svelte)|\./[a-zA-Z0-9_.-]+\.(ts|js|py|go|rs|java|rb|sh|yaml|yml|json|toml|tsx|jsx|css|scss|html|sql|c|cpp|h|hpp|swift|kt|vue|svelte)' | \
        sed 's/^`//; s/`$//' | \
        grep -v '^\(http\|https\|www\)' | \
        sort -u
}

# Extract backticked code identifiers (functions, classes, methods)
# Patterns: `functionName()`, `ClassName`, `module.method()`
extract_code_refs() {
    local text="$1"
    echo "$text" | grep -oE '`[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*\(\)`|`[A-Z][a-zA-Z0-9_]+`' | \
        sed 's/^`//; s/`$//; s/()$//' | \
        grep -v '^[A-Z][A-Z_]*$' | \
        sort -u
}

# Check if a file reference exists relative to node directory
# Returns: "found" or "not_found"
check_file_exists() {
    local node_dir="$1"
    local file_ref="$2"

    # Try multiple resolution strategies
    # 1. Relative to node directory
    if [[ -f "$node_dir/$file_ref" ]]; then
        echo "found"
        return
    fi

    # 2. Relative to repo root
    if [[ -n "$REPO_ROOT" ]] && [[ -f "$REPO_ROOT/$file_ref" ]]; then
        echo "found"
        return
    fi

    # 3. Search in node directory tree
    if find "$node_dir" -name "$(basename "$file_ref")" -type f 2>/dev/null | grep -q .; then
        echo "found"
        return
    fi

    echo "not_found"
}

# Check if a code identifier exists in the codebase
# Returns: "found" or "not_found"
check_code_exists() {
    local node_dir="$1"
    local code_ref="$2"

    # Strip method calls (e.g., "obj.method" -> search for "method")
    local search_term="${code_ref##*.}"

    # Build grep pattern - look for function/class/method definitions
    local pattern="(function|def|class|const|let|var|export).*\\b${search_term}\\b|\\b${search_term}\\s*[=(]"

    # Search in node directory
    if grep -rE "$pattern" "$node_dir" --include="*.ts" --include="*.js" --include="*.py" \
       --include="*.go" --include="*.rs" --include="*.java" --include="*.rb" 2>/dev/null | grep -q .; then
        echo "found"
        return
    fi

    # Also search in repo root if different
    if [[ -n "$REPO_ROOT" ]] && [[ "$REPO_ROOT" != "$node_dir" ]]; then
        if grep -rE "$pattern" "$REPO_ROOT" --include="*.ts" --include="*.js" --include="*.py" \
           --include="*.go" --include="*.rs" --include="*.java" --include="*.rb" 2>/dev/null | head -1 | grep -q .; then
            echo "found"
            return
        fi
    fi

    echo "not_found"
}

# Parse entries from a section
# An entry is typically a list item or table row
parse_section_entries() {
    local section_content="$1"

    # Extract list items (- or *) and table rows (|)
    echo "$section_content" | grep -E '^\s*[-*]|^\|[^-]' | \
        sed 's/^\s*[-*]\s*//; s/^\|//; s/\|$//' | \
        grep -v '^\s*$'
}

# Check a single entry for stale references
# Output format: "STALE|type|reference|reason" or empty if valid
check_entry_references() {
    local node_dir="$1"
    local entry_text="$2"
    local quick_mode="$3"

    local stale_refs=()

    # Extract and check file references
    local file_refs
    file_refs=$(extract_file_refs "$entry_text")

    for ref in $file_refs; do
        [[ -z "$ref" ]] && continue
        local status
        status=$(check_file_exists "$node_dir" "$ref")
        if [[ "$status" == "not_found" ]]; then
            stale_refs+=("file|$ref|not found")
        fi
    done

    # Extract and check code references (unless quick mode)
    if [[ "$quick_mode" != "true" ]]; then
        local code_refs
        code_refs=$(extract_code_refs "$entry_text")

        for ref in $code_refs; do
            [[ -z "$ref" ]] && continue
            local status
            status=$(check_code_exists "$node_dir" "$ref")
            if [[ "$status" == "not_found" ]]; then
                stale_refs+=("code|$ref|not found in codebase")
            fi
        done
    fi

    # Output stale references
    for stale in "${stale_refs[@]}"; do
        echo "$stale"
    done
}

# Truncate text for display
truncate_text() {
    local text="$1"
    local max_len="${2:-50}"

    text=$(echo "$text" | tr '\n' ' ' | sed 's/  */ /g')
    if [[ ${#text} -gt $max_len ]]; then
        echo "${text:0:$((max_len-3))}..."
    else
        echo "$text"
    fi
}

# Check all entries in a node for staleness
# Outputs: first line is count, remaining lines are report
check_node_entries() {
    local node_path="$1"
    local quick_mode="$2"

    local node_dir
    node_dir=$(dirname "$node_path")

    local stale_count=0
    local report=""

    # Check each reference section
    local sections=("Pitfalls" "Contracts" "Entry Points" "Patterns" "Code Map" "Public API" "Architecture")

    for section in "${sections[@]}"; do
        local section_content
        section_content=$(extract_section "$node_path" "$section")

        [[ -z "$section_content" ]] && continue

        local entries
        entries=$(parse_section_entries "$section_content")

        [[ -z "$entries" ]] && continue

        local section_stale=""

        while IFS= read -r entry; do
            [[ -z "$entry" ]] && continue

            local stale_refs
            stale_refs=$(check_entry_references "$node_dir" "$entry" "$quick_mode")

            if [[ -n "$stale_refs" ]]; then
                local entry_display
                entry_display=$(truncate_text "$entry" 40)

                while IFS='|' read -r ref_type ref_name reason; do
                    [[ -z "$ref_type" ]] && continue
                    stale_count=$((stale_count + 1))
                    section_stale+="      X \"$entry_display\" - $ref_name ($reason)"$'\n'
                done <<< "$stale_refs"
            fi
        done <<< "$entries"

        if [[ -n "$section_stale" ]]; then
            report+="    Section: $section"$'\n'
            report+="$section_stale"
        fi
    done

    # Output count on first line, then report
    echo "$stale_count"
    if [[ -n "$report" ]]; then
        printf '%s' "$report"
    fi
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

# ============================================================================
# Main execution
# ============================================================================

# Collect all nodes
declare -a ALL_NODES=()
while IFS= read -r node; do
    [ -z "$node" ] && continue
    ALL_NODES+=("$node")
done < <(find_nodes)

# Entry-level staleness check
if [ "$CHECK_ENTRIES" = true ]; then
    if [ "$QUIET" = false ]; then
        echo "Entry Staleness Report"
        echo "======================"
        echo ""
        echo "Scanned: $TARGET_PATH"
        [ "$ENTRIES_QUICK" = true ] && echo "Mode: quick (file paths only)"
        [ "$ENTRIES_QUICK" = false ] && echo "Mode: full (file paths + code identifiers)"
        echo ""
    fi

    total_stale_entries=0
    nodes_with_stale=0
    declare -a ENTRY_REPORTS=()

    for node in "${ALL_NODES[@]}"; do
        # Capture output: first line is count, rest is report
        entry_output=$(check_node_entries "$node" "$ENTRIES_QUICK")
        stale_count=$(echo "$entry_output" | head -1)
        report=$(echo "$entry_output" | tail -n +2)

        # Get node age for context
        days_old=$(days_since_modified "$node")

        node_status="fresh"
        if [ "$days_old" -gt "$THRESHOLD" ]; then
            node_status="stale (${days_old}d)"
        else
            node_status="fresh (${days_old}d)"
        fi

        # Make path relative for display
        rel_path="${node#$TARGET_PATH/}"

        if [ "$stale_count" -gt 0 ]; then
            total_stale_entries=$((total_stale_entries + stale_count))
            nodes_with_stale=$((nodes_with_stale + 1))

            if [ "$QUIET" = true ]; then
                echo "$node"
            else
                echo "$rel_path (node: $node_status, entries: $stale_count stale)"
                if [[ -n "$report" ]]; then
                    echo "$report"
                fi
                echo ""
            fi
        else
            if [ "$QUIET" = false ]; then
                echo "$rel_path (node: $node_status, entries: 0 stale)"
                echo "    All entry references verified"
                echo ""
            fi
        fi
    done

    if [ "$QUIET" = false ]; then
        echo "---"
        echo ""
        echo "Summary: $total_stale_entries stale entries across $nodes_with_stale node(s)"
        echo ""
        if [ "$total_stale_entries" -gt 0 ]; then
            echo "**Recommended**: Update or remove stale entries. References may point to:"
            echo "  - Deleted/renamed files"
            echo "  - Refactored functions/classes"
            echo "  - Moved code"
        fi
    fi

    if [ "$total_stale_entries" -gt 0 ]; then
        exit 2
    fi
    exit 0
fi

# Standard node-level staleness check
declare -a STALE_NODES=()

for node in "${ALL_NODES[@]}"; do
    result=$(check_node_staleness "$node")
    [ -n "$result" ] && STALE_NODES+=("$result")
done

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
        echo "V No stale nodes found."
        echo ""
        echo "**Tip**: Use --entries to check for stale individual entries within fresh nodes."
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
    echo ""
    echo "**Tip**: Use --entries to check for stale individual entries within fresh nodes."
fi

# Exit with code 2 if stale nodes found (useful for CI)
exit 2
