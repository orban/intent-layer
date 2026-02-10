#!/usr/bin/env bash
set -euo pipefail

# learn.sh - Direct-write learning to AGENTS.md with dedup quality gate
#
# Usage: learn.sh --project <path> --path <file> --type <type> --title <text> --detail <text>
#
# Writes learnings directly into the covering AGENTS.md file, using word-overlap
# deduplication to prevent duplicates. Designed for single-agent sessions.
# For multi-agent swarms, use report_learning.sh instead (pending queue).
#
# Required:
#   --project PATH    Project root directory
#   --path FILE       File or directory the learning relates to
#   --type TYPE       Learning type: pitfall, check, pattern, insight
#   --title TEXT      Short title (used as ### header)
#   --detail TEXT     Body content for the entry
#
# Optional:
#   --dry-run         Show what would be written without modifying files
#   --check-only      Only check for duplicates (exit 0 = novel, 2 = duplicate)
#   --agent-id ID     Rejected — prints error directing to report_learning.sh
#   -h, --help        Show this help
#
# Exit codes:
#   0    Learning integrated (or novel with --check-only, or --dry-run)
#   1    Error (missing args, no covering node, etc.)
#   2    Duplicate skipped (≥60% word overlap with existing entry)
#
# Examples:
#   learn.sh --project /repo --path src/api/ --type pitfall \
#     --title "Null check on empty collections" \
#     --detail "API returns null instead of empty array for empty results"
#
#   learn.sh --project /repo --path src/db/ --type check --dry-run \
#     --title "Verify backup before migration" \
#     --detail "Lost data when migration failed without backup"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

PROJECT=""
FILE_PATH=""
LEARNING_TYPE=""
TITLE=""
DETAIL=""
DRY_RUN=false
CHECK_ONLY=false
OVERLAP_THRESHOLD=60

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --project) PROJECT="$2"; shift 2 ;;
        --path) FILE_PATH="$2"; shift 2 ;;
        --type) LEARNING_TYPE="$2"; shift 2 ;;
        --title) TITLE="$2"; shift 2 ;;
        --detail) DETAIL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --check-only) CHECK_ONLY=true; shift ;;
        --agent-id)
            echo "Error: --agent-id is not supported by learn.sh (direct-write is single-agent only)" >&2
            echo "Hint: Use report_learning.sh for swarm workers" >&2
            exit 1
            ;;
        *) echo "Error: Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Validate required args
MISSING=""
[[ -z "$PROJECT" ]] && MISSING="$MISSING --project"
[[ -z "$FILE_PATH" ]] && MISSING="$MISSING --path"
[[ -z "$LEARNING_TYPE" ]] && MISSING="$MISSING --type"
[[ -z "$TITLE" ]] && MISSING="$MISSING --title"
[[ -z "$DETAIL" ]] && MISSING="$MISSING --detail"

if [[ -n "$MISSING" ]]; then
    echo "Error: Missing required arguments:$MISSING" >&2
    echo "Usage: learn.sh --project <path> --path <file> --type <type> --title <text> --detail <text>" >&2
    exit 1
fi

# Validate project directory
if [[ ! -d "$PROJECT" ]]; then
    echo "Error: Project directory not found: $PROJECT" >&2
    exit 1
fi

# Validate type
case "$LEARNING_TYPE" in
    pitfall|check|pattern|insight) ;;
    *) echo "Error: Invalid type '$LEARNING_TYPE'. Must be: pitfall, check, pattern, insight" >&2; exit 1 ;;
esac

# Resolve file path
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="$PROJECT/$FILE_PATH"
fi

# Map type → section
case "$LEARNING_TYPE" in
    pitfall) TARGET_SECTION="Pitfalls" ;;
    check)   TARGET_SECTION="Checks" ;;
    pattern) TARGET_SECTION="Patterns" ;;
    insight) TARGET_SECTION="Context" ;;
esac

# Format entry (matches integrate_pitfall.sh formatting)
case "$LEARNING_TYPE" in
    check)
        ENTRY="### Before $TITLE
- [ ] $DETAIL

_Source: learn.sh_"
        ;;
    pattern)
        ENTRY="### $TITLE

**Preferred**: $DETAIL

_Source: learn.sh_"
        ;;
    *)
        # pitfall and insight share the same format
        ENTRY="### $TITLE

$DETAIL

_Source: learn.sh_"
        ;;
esac

# Find covering node
FIND_NODE="$SCRIPT_DIR/../lib/find_covering_node.sh"
if [[ ! -x "$FIND_NODE" ]]; then
    echo "Error: find_covering_node.sh not found at $FIND_NODE" >&2
    exit 1
fi

export CLAUDE_PROJECT_DIR="$PROJECT"
COVERING_NODE=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

if [[ -z "$COVERING_NODE" ]]; then
    echo "Error: No covering AGENTS.md found for $FILE_PATH" >&2
    echo "Hint: Create an AGENTS.md in or above this directory first" >&2
    exit 1
fi

# Inline dedup: check existing ### headers in target section for overlap
if grep -q "^## $TARGET_SECTION" "$COVERING_NODE" 2>/dev/null; then
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        # Strip the ### prefix
        existing_title="${line#\#\#\# }"
        # Also strip "Before " prefix for check entries
        existing_title="${existing_title#Before }"
        overlap=$(calculate_word_overlap "$TITLE" "$existing_title")
        if [[ "$overlap" -ge "$OVERLAP_THRESHOLD" ]]; then
            if $CHECK_ONLY; then
                echo "Duplicate found (${overlap}% overlap): $existing_title" >&2
                exit 2
            fi
            echo "Duplicate skipped (${overlap}% overlap with existing: $existing_title)" >&2
            exit 2
        fi
    done < <(awk -v section="$TARGET_SECTION" '
        /^## / {
            if (in_section) exit
            if ($0 == "## " section) { in_section=1; next }
        }
        in_section && /^### / { print }
    ' "$COVERING_NODE")
fi

# --check-only with no duplicate found
if $CHECK_ONLY; then
    echo "No duplicate found"
    exit 0
fi

# --dry-run: show what would be written
if $DRY_RUN; then
    echo "[DRY RUN] Would append to ## $TARGET_SECTION in: $COVERING_NODE"
    echo "---"
    echo "$ENTRY"
    echo "---"
    exit 0
fi

# Create section if missing
if ! grep -q "^## $TARGET_SECTION" "$COVERING_NODE"; then
    echo "" >> "$COVERING_NODE"
    echo "## $TARGET_SECTION" >> "$COVERING_NODE"
    echo "" >> "$COVERING_NODE"
fi

# Insert entry after section header using temp-file swap
TEMP_FILE=$(mktemp)
ENTRY_FILE=$(mktemp)

printf '%s\n\n' "$ENTRY" > "$ENTRY_FILE"

SECTION_LINE=$(grep -n "^## $TARGET_SECTION" "$COVERING_NODE" | head -1 | cut -d: -f1)

if [[ -z "$SECTION_LINE" ]]; then
    echo "Error: Could not find ## $TARGET_SECTION section after creation" >&2
    rm -f "$ENTRY_FILE" "$TEMP_FILE"
    exit 1
fi

NEXT_LINE=$((SECTION_LINE + 1))
TOTAL_LINES=$(wc -l < "$COVERING_NODE" | tr -d ' ')

head -n "$NEXT_LINE" "$COVERING_NODE" > "$TEMP_FILE"
# Ensure blank line before entry
[[ $(tail -c 1 "$TEMP_FILE" | wc -l) -eq 0 ]] && echo "" >> "$TEMP_FILE"
cat "$ENTRY_FILE" >> "$TEMP_FILE"
# Append rest of file if any
if [[ "$NEXT_LINE" -lt "$TOTAL_LINES" ]]; then
    tail -n "+$((NEXT_LINE + 1))" "$COVERING_NODE" >> "$TEMP_FILE"
fi

rm -f "$ENTRY_FILE"
mv "$TEMP_FILE" "$COVERING_NODE"

echo "✓ $LEARNING_TYPE added to ## $TARGET_SECTION in $COVERING_NODE"
