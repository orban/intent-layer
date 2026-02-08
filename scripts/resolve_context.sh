#!/usr/bin/env bash
set -euo pipefail

# resolve_context.sh - Single-call context resolver for agent swarms
#
# Usage: resolve_context.sh <project_root> <target_path> [options]
#
# Returns merged context from all ancestor AGENTS.md/CLAUDE.md nodes for a
# given path. Designed for swarm workers that need full context in one call.
#
# Arguments:
#   project_root   Path to the project root (where root CLAUDE.md lives)
#   target_path    Relative path (or absolute) to resolve context for
#
# Options:
#   --sections LIST   Comma-separated sections to include (default: all)
#                     Example: --sections "Contracts,Pitfalls,Checks"
#   --compact         Omit section headers and hierarchy info, just content
#   --with-pending    Include pending learning reports for this area
#   -h, --help        Show this help
#
# Output:
#   Markdown text with merged context from all ancestor nodes.
#   Sections are deduplicated: child entries override/supplement parent.
#
# Exit codes:
#   0 - Success (context returned)
#   1 - Error (invalid args, project not found)
#   2 - No coverage (target path has no covering node)
#
# Examples:
#   resolve_context.sh /project src/api/
#   resolve_context.sh /project src/api/routes/users.ts --sections "Contracts,Pitfalls"
#   resolve_context.sh /project src/api/ --compact

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Defaults
SECTIONS_FILTER=""
COMPACT=false
WITH_PENDING=false

POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --sections) SECTIONS_FILTER="$2"; shift 2 ;;
        --compact) COMPACT=true; shift ;;
        --with-pending) WITH_PENDING=true; shift ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [[ $# -lt 2 ]]; then
    echo "Error: Missing required arguments" >&2
    echo "Usage: resolve_context.sh <project_root> <target_path>" >&2
    exit 1
fi

PROJECT_ROOT="$1"
TARGET_PATH="$2"

if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Error: Project root not found: $PROJECT_ROOT" >&2
    exit 1
fi

PROJECT_ROOT=$(cd "$PROJECT_ROOT" && pwd)

# Resolve target to absolute path
if [[ "$TARGET_PATH" != /* ]]; then
    TARGET_PATH="$PROJECT_ROOT/$TARGET_PATH"
fi

# Strip trailing slash, resolve to directory
if [[ -f "$TARGET_PATH" ]]; then
    TARGET_DIR=$(dirname "$TARGET_PATH")
elif [[ -d "$TARGET_PATH" ]]; then
    TARGET_DIR="$TARGET_PATH"
else
    # Path doesn't exist yet — walk up until we find an existing directory
    TARGET_DIR=$(dirname "$TARGET_PATH")
    while [[ ! -d "$TARGET_DIR" && "$TARGET_DIR" != "/" ]]; do
        TARGET_DIR=$(dirname "$TARGET_DIR")
    done
    if [[ ! -d "$TARGET_DIR" ]]; then
        echo "Error: Cannot resolve path: $TARGET_PATH" >&2
        exit 1
    fi
fi

TARGET_DIR=$(cd "$TARGET_DIR" && pwd)

# --- Collect ancestor nodes (root-first order) ---

collect_ancestors_root_first() {
    local current="$TARGET_DIR"
    local nodes=()

    # Walk up to project root, collecting nodes
    while [[ "$current" != "/" ]]; do
        if [[ -f "$current/AGENTS.md" ]]; then
            nodes+=("$current/AGENTS.md")
        elif [[ -f "$current/CLAUDE.md" ]]; then
            nodes+=("$current/CLAUDE.md")
        fi
        # Stop at project root
        [[ "$current" == "$PROJECT_ROOT" ]] && break
        current=$(dirname "$current")
    done

    # Reverse to get root-first order
    local i
    for (( i=${#nodes[@]}-1; i>=0; i-- )); do
        echo "${nodes[$i]}"
    done
}

NODES=$(collect_ancestors_root_first)

# Check coverage: a path is "uncovered" if no nodes found OR
# if the only node is the project root and the target is not the root itself
_no_coverage=false
if [[ -z "$NODES" ]]; then
    _no_coverage=true
elif [[ "$TARGET_DIR" != "$PROJECT_ROOT" ]]; then
    # Count nodes; if only node is the root CLAUDE.md, path has no specific coverage
    NODE_COUNT=$(echo "$NODES" | grep -c .)
    FIRST_NODE=$(echo "$NODES" | head -1)
    if [[ "$NODE_COUNT" -eq 1 && "$FIRST_NODE" == "$PROJECT_ROOT/CLAUDE.md" ]]; then
        _no_coverage=true
    fi
fi

if [[ "$_no_coverage" == "true" ]]; then
    # Output to both stdout (for callers capturing output) and stderr (for terminals)
    echo "## No Intent Layer Coverage"
    echo ""
    echo "No covering node found for: ${TARGET_DIR#$PROJECT_ROOT/}"
    echo "Run \`/intent-layer\` to set up coverage."
    echo "## No Intent Layer Coverage" >&2
    echo "No covering node found for: ${TARGET_DIR#$PROJECT_ROOT/}" >&2
    exit 2
fi

# --- Extract sections from a node ---

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
            if (tolower($0) ~ "^##+ *" tolower(section) "$") {
                in_section = 1
                match($0, /^#+/)
                level = RLENGTH
            }
        }
        in_section { print }
    ' "$file"
}

# Standard sections to look for
ALL_SECTIONS="Purpose,Entry Points,Contracts,Pitfalls,Checks,Patterns,Boundaries,Design Rationale,Code Map,Public API,Downlinks,Context"

# Apply filter
if [[ -n "$SECTIONS_FILTER" ]]; then
    ACTIVE_SECTIONS="$SECTIONS_FILTER"
else
    ACTIVE_SECTIONS="$ALL_SECTIONS"
fi

# --- Build output ---

OUTPUT=""

if [[ "$COMPACT" != "true" ]]; then
    REL_TARGET="${TARGET_DIR#$PROJECT_ROOT/}"
    [[ "$REL_TARGET" == "$TARGET_DIR" ]] && REL_TARGET="(root)"

    OUTPUT="# Intent Layer Context: $REL_TARGET"
    OUTPUT="$OUTPUT

**Hierarchy:**"

    while IFS= read -r node; do
        [[ -z "$node" ]] && continue
        REL_NODE="${node#$PROJECT_ROOT/}"
        OUTPUT="$OUTPUT
- \`$REL_NODE\`"
    done <<< "$NODES"
    OUTPUT="$OUTPUT
"
fi

# Collect sections across all nodes, child supplements parent
declare -A SECTION_CONTENT

IFS=',' read -ra SECTION_LIST <<< "$ACTIVE_SECTIONS"

for section in "${SECTION_LIST[@]}"; do
    section=$(echo "$section" | sed 's/^ *//;s/ *$//')  # trim whitespace
    MERGED=""

    while IFS= read -r node; do
        [[ -z "$node" ]] && continue
        CONTENT=$(extract_section "$node" "$section")
        if [[ -n "$CONTENT" ]]; then
            REL_NODE="${node#$PROJECT_ROOT/}"
            if [[ -n "$MERGED" ]]; then
                if [[ "$COMPACT" == "true" ]]; then
                    # In compact mode, just append content lines (skip header)
                    MERGED="$MERGED
$(echo "$CONTENT" | tail -n +2)"
                else
                    MERGED="$MERGED

_From \`$REL_NODE\`:_
$(echo "$CONTENT" | tail -n +2)"
                fi
            else
                if [[ "$COMPACT" == "true" ]]; then
                    MERGED="$CONTENT"
                else
                    MERGED="_From \`$REL_NODE\`:_
$CONTENT"
                fi
            fi
        fi
    done <<< "$NODES"

    if [[ -n "$MERGED" ]]; then
        if [[ "$COMPACT" == "true" ]]; then
            OUTPUT="$OUTPUT
$MERGED
"
        else
            OUTPUT="$OUTPUT
$MERGED
"
        fi
    fi
done

# --- Include pending learnings if requested ---

if [[ "$WITH_PENDING" == "true" ]]; then
    PENDING_DIR="$PROJECT_ROOT/.intent-layer/mistakes/pending"
    if [[ -d "$PENDING_DIR" ]]; then
        REL_TARGET="${TARGET_DIR#$PROJECT_ROOT/}"
        PENDING_FILES=$(find "$PENDING_DIR" -name "*.md" -type f 2>/dev/null | sort)
        RELEVANT=""

        while IFS= read -r pf; do
            [[ -z "$pf" ]] && continue
            if grep -q "$REL_TARGET\|$TARGET_DIR" "$pf" 2>/dev/null; then
                RELEVANT="$RELEVANT
- \`$(basename "$pf")\`"
            fi
        done <<< "$PENDING_FILES"

        if [[ -n "$RELEVANT" ]]; then
            OUTPUT="$OUTPUT
## Pending Learnings (Unreviewed)
$RELEVANT
"
        fi
    fi
fi

echo "$OUTPUT"
