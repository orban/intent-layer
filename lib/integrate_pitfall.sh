#!/usr/bin/env bash
# Integrate an accepted learning into the covering AGENTS.md
# Usage: integrate_pitfall.sh <learning_file>
# Note: Name kept for backwards compatibility - handles all learning types

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

show_help() {
    cat << 'EOF'
integrate_pitfall.sh - Add learning to appropriate AGENTS.md section

USAGE:
    integrate_pitfall.sh <learning_file> [OPTIONS]

ARGUMENTS:
    learning_file   Path to accepted learning report (PITFALL-*.md, CHECK-*.md, etc.)

OPTIONS:
    -h, --help           Show this help
    -n, --dry-run        Show what would be done without modifying files
    -f, --force          Overwrite even if entry seems to exist
    -s, --section NAME   Override target section (Pitfalls, Checks, Patterns, Context)

LEARNING TYPES → TARGET SECTIONS:
    pitfall  → ## Pitfalls
    check    → ## Checks
    pattern  → ## Patterns
    insight  → ## Context

WORKFLOW:
    1. Reads the accepted learning report
    2. Detects learning type from report
    3. Finds the covering AGENTS.md using find_covering_node.sh
    4. Extracts/generates an entry for the appropriate section
    5. Appends to the target section (creates if missing)
    6. Moves report to .intent-layer/mistakes/integrated/

EXIT CODES:
    0    Learning integrated successfully
    1    Error (file not found, no covering node, etc.)
    2    Entry already exists (use --force to override)
EOF
    exit 0
}

LEARNING_FILE=""
DRY_RUN=false
FORCE=false
OVERRIDE_SECTION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        -f|--force) FORCE=true; shift ;;
        -s|--section) OVERRIDE_SECTION="$2"; shift 2 ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            LEARNING_FILE="$1"
            shift
            ;;
    esac
done

if [[ -z "$LEARNING_FILE" ]]; then
    echo "Error: Learning file required" >&2
    echo "Usage: integrate_pitfall.sh <learning_file>" >&2
    exit 1
fi

if [[ ! -f "$LEARNING_FILE" ]]; then
    echo "Error: File not found: $LEARNING_FILE" >&2
    exit 1
fi

# Backwards compatibility alias
MISTAKE_FILE="$LEARNING_FILE"

# Extract fields from mistake report
extract_field() {
    local file="$1"
    local pattern="$2"
    grep -m1 "$pattern" "$file" 2>/dev/null | sed 's/.*: //' || echo ""
}

extract_section() {
    local file="$1"
    local section="$2"
    awk -v section="$section" '
        /^### / {
            if (found) exit
            if ($0 == "### " section) { found=1; next }
        }
        found && /^### / { exit }
        found { print }
    ' "$file" | sed '/^$/d' | head -10
}

# Detect learning type from filename or content
LEARNING_TYPE=""
FILENAME=$(basename "$LEARNING_FILE")
case "$FILENAME" in
    PITFALL-*|MISTAKE-*|SKELETON-*) LEARNING_TYPE="pitfall" ;;
    CHECK-*)    LEARNING_TYPE="check" ;;
    PATTERN-*)  LEARNING_TYPE="pattern" ;;
    INSIGHT-*)  LEARNING_TYPE="insight" ;;
    *)
        # Try to extract from file content
        LEARNING_TYPE=$(extract_field "$LEARNING_FILE" '^\*\*Type\*\*')
        LEARNING_TYPE=${LEARNING_TYPE:-pitfall}
        ;;
esac

echo "Detected learning type: $LEARNING_TYPE"

# Map learning type to target section
if [[ -n "$OVERRIDE_SECTION" ]]; then
    TARGET_SECTION="$OVERRIDE_SECTION"
else
    case "$LEARNING_TYPE" in
        pitfall) TARGET_SECTION="Pitfalls" ;;
        check)   TARGET_SECTION="Checks" ;;
        pattern) TARGET_SECTION="Patterns" ;;
        insight) TARGET_SECTION="Context" ;;
        *)       TARGET_SECTION="Pitfalls" ;;
    esac
fi

echo "Target section: ## $TARGET_SECTION"

DIRECTORY=$(extract_field "$LEARNING_FILE" '^\*\*Directory\*\*')
OPERATION=$(extract_field "$LEARNING_FILE" '^\*\*Operation\*\*')

# Extract content based on learning type - try multiple section names
WHAT_HAPPENED=$(extract_section "$LEARNING_FILE" "What Happened")
[[ -z "$WHAT_HAPPENED" ]] && WHAT_HAPPENED=$(extract_section "$LEARNING_FILE" "What Went Wrong")
[[ -z "$WHAT_HAPPENED" ]] && WHAT_HAPPENED=$(extract_section "$LEARNING_FILE" "Check Needed")
[[ -z "$WHAT_HAPPENED" ]] && WHAT_HAPPENED=$(extract_section "$LEARNING_FILE" "Better Approach")
[[ -z "$WHAT_HAPPENED" ]] && WHAT_HAPPENED=$(extract_section "$LEARNING_FILE" "Key Insight")

ROOT_CAUSE=$(extract_section "$LEARNING_FILE" "Root Cause")
[[ -z "$ROOT_CAUSE" ]] && ROOT_CAUSE=$(extract_section "$LEARNING_FILE" "Why This Matters")

SUGGESTED_FIX=$(extract_section "$LEARNING_FILE" "Suggested Fix")
[[ -z "$SUGGESTED_FIX" ]] && SUGGESTED_FIX=$(extract_section "$LEARNING_FILE" "Suggested Pitfall Entry")
[[ -z "$SUGGESTED_FIX" ]] && SUGGESTED_FIX=$(extract_section "$LEARNING_FILE" "Suggested Check Entry")
[[ -z "$SUGGESTED_FIX" ]] && SUGGESTED_FIX=$(extract_section "$LEARNING_FILE" "Suggested Pattern Entry")
[[ -z "$SUGGESTED_FIX" ]] && SUGGESTED_FIX=$(extract_section "$LEARNING_FILE" "Suggested Context Entry")

if [[ -z "$DIRECTORY" || "$DIRECTORY" == "unknown" ]]; then
    echo "Error: Cannot determine directory from mistake report" >&2
    exit 1
fi

# Find covering node
FIND_NODE="$SCRIPT_DIR/find_covering_node.sh"
if [[ ! -x "$FIND_NODE" ]]; then
    echo "Error: find_covering_node.sh not found" >&2
    exit 1
fi

COVERING_NODE=$("$FIND_NODE" "$DIRECTORY" 2>/dev/null || true)

if [[ -z "$COVERING_NODE" ]]; then
    echo "Error: No covering AGENTS.md found for $DIRECTORY" >&2
    echo "Hint: Create an AGENTS.md in or above this directory first" >&2
    exit 1
fi

echo "Found covering node: $COVERING_NODE"

# Generate entry based on learning type
ENTRY_TITLE=""
ENTRY_BODY=""

if [[ -n "$SUGGESTED_FIX" && "$SUGGESTED_FIX" != "_Awaiting analysis_" ]]; then
    ENTRY_TITLE=$(echo "$OPERATION" | sed 's/[^a-zA-Z0-9 ]//g' | head -c 50)
    ENTRY_BODY="$ROOT_CAUSE"
elif [[ -n "$ROOT_CAUSE" && "$ROOT_CAUSE" != "_Awaiting analysis_" ]]; then
    ENTRY_TITLE=$(echo "$OPERATION" | sed 's/[^a-zA-Z0-9 ]//g' | head -c 50)
    ENTRY_BODY="$ROOT_CAUSE"
else
    ENTRY_TITLE=$(echo "$OPERATION" | sed 's/[^a-zA-Z0-9 ]//g' | head -c 50)
    ENTRY_BODY="$WHAT_HAPPENED"
fi

# Clean up the entry
ENTRY_TITLE=$(echo "$ENTRY_TITLE" | sed 's/^ *//;s/ *$//')
ENTRY_BODY=$(echo "$ENTRY_BODY" | tr '\n' ' ' | sed 's/  */ /g;s/^ *//;s/ *$//' | head -c 200)

if [[ -z "$ENTRY_TITLE" ]]; then
    ENTRY_TITLE="Untitled $LEARNING_TYPE"
fi

# Format entry based on learning type
case "$LEARNING_TYPE" in
    check)
        # Checks are formatted as checklists
        LEARNING_ENTRY="### Before $ENTRY_TITLE
- [ ] $ENTRY_BODY

_Source: $(basename "$LEARNING_FILE")_"
        ;;
    pattern)
        # Patterns show the preferred approach
        LEARNING_ENTRY="### $ENTRY_TITLE

**Preferred**: $ENTRY_BODY

_Source: $(basename "$LEARNING_FILE")_"
        ;;
    insight)
        # Insights are contextual notes
        LEARNING_ENTRY="### $ENTRY_TITLE

$ENTRY_BODY

_Source: $(basename "$LEARNING_FILE")_"
        ;;
    *)
        # Default pitfall format
        LEARNING_ENTRY="### $ENTRY_TITLE

$ENTRY_BODY

_Source: $(basename "$LEARNING_FILE")_"
        ;;
esac

echo ""
echo "Generated $LEARNING_TYPE entry:"
echo "---"
echo "$LEARNING_ENTRY"
echo "---"
echo ""

# Check if similar entry already exists
if ! $FORCE; then
    if grep -qi "$(echo "$ENTRY_TITLE" | head -c 20)" "$COVERING_NODE" 2>/dev/null; then
        echo "Warning: Similar entry may already exist in $COVERING_NODE" >&2
        echo "Use --force to add anyway" >&2
        exit 2
    fi
fi

if $DRY_RUN; then
    echo "[DRY RUN] Would append to ## $TARGET_SECTION in: $COVERING_NODE"
    echo "[DRY RUN] Would move $LEARNING_FILE to integrated/"
    exit 0
fi

# Check if target section exists, create if not
if ! grep -q "^## $TARGET_SECTION" "$COVERING_NODE"; then
    echo "Adding ## $TARGET_SECTION section to $COVERING_NODE"
    echo "" >> "$COVERING_NODE"
    echo "## $TARGET_SECTION" >> "$COVERING_NODE"
    echo "" >> "$COVERING_NODE"
fi

# Append entry after the target section header
TEMP_FILE=$(mktemp)
ENTRY_FILE=$(mktemp)

# Write entry to temp file (preserves newlines properly)
printf '%s\n\n' "$LEARNING_ENTRY" > "$ENTRY_FILE"

# Find the line number of the target section
SECTION_LINE=$(grep -n "^## $TARGET_SECTION" "$COVERING_NODE" | head -1 | cut -d: -f1)

if [[ -z "$SECTION_LINE" ]]; then
    echo "Error: Could not find ## $TARGET_SECTION section" >&2
    rm -f "$ENTRY_FILE"
    exit 1
fi

# Insert after the section header (skip one blank line if present)
NEXT_LINE=$((SECTION_LINE + 1))
TOTAL_LINES=$(wc -l < "$COVERING_NODE" | tr -d ' ')

# Get everything up to the line after the section header
head -n "$NEXT_LINE" "$COVERING_NODE" > "$TEMP_FILE"
# Add blank line if not already present
[[ $(tail -c 1 "$TEMP_FILE" | wc -l) -eq 0 ]] && echo "" >> "$TEMP_FILE"
# Add the entry
cat "$ENTRY_FILE" >> "$TEMP_FILE"
# Add the rest of the file (if any)
if [[ "$NEXT_LINE" -lt "$TOTAL_LINES" ]]; then
    tail -n "+$((NEXT_LINE + 1))" "$COVERING_NODE" >> "$TEMP_FILE"
fi

rm -f "$ENTRY_FILE"
mv "$TEMP_FILE" "$COVERING_NODE"
echo "✓ $LEARNING_TYPE added to ## $TARGET_SECTION in $COVERING_NODE"

# Move learning to integrated
LEARNING_DIR=$(dirname "$LEARNING_FILE")
INTEGRATED_DIR="${LEARNING_DIR%/pending}/integrated"
mkdir -p "$INTEGRATED_DIR"

# Mark as integrated in the file (try various formats)
sed -i.bak 's/- \[ \] Pitfall added/- [x] Pitfall added/' "$LEARNING_FILE" 2>/dev/null || \
    sed -i '' 's/- \[ \] Pitfall added/- [x] Pitfall added/' "$LEARNING_FILE" 2>/dev/null || true
sed -i.bak 's/- \[ \] Added to AGENTS.md/- [x] Added to AGENTS.md/' "$LEARNING_FILE" 2>/dev/null || \
    sed -i '' 's/- \[ \] Added to AGENTS.md/- [x] Added to AGENTS.md/' "$LEARNING_FILE" 2>/dev/null || true
rm -f "$LEARNING_FILE.bak"

mv "$LEARNING_FILE" "$INTEGRATED_DIR/"
echo "✓ Moved to $INTEGRATED_DIR/"

echo ""
echo "Integration complete! ($LEARNING_TYPE → ## $TARGET_SECTION)"
