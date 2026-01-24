#!/usr/bin/env bash
# Integrate an accepted mistake into the covering AGENTS.md
# Usage: integrate_pitfall.sh <mistake_file>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

show_help() {
    cat << 'EOF'
integrate_pitfall.sh - Add pitfall from accepted mistake to AGENTS.md

USAGE:
    integrate_pitfall.sh <mistake_file> [OPTIONS]

ARGUMENTS:
    mistake_file    Path to accepted MISTAKE-*.md file

OPTIONS:
    -h, --help           Show this help
    -n, --dry-run        Show what would be done without modifying files
    -f, --force          Overwrite even if pitfall seems to exist

WORKFLOW:
    1. Reads the accepted mistake report
    2. Finds the covering AGENTS.md using find_covering_node.sh
    3. Extracts/generates a pitfall entry
    4. Appends to the ## Pitfalls section
    5. Moves mistake to .intent-layer/mistakes/integrated/

EXIT CODES:
    0    Pitfall integrated successfully
    1    Error (file not found, no covering node, etc.)
    2    Pitfall already exists (use --force to override)
EOF
    exit 0
}

MISTAKE_FILE=""
DRY_RUN=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        -f|--force) FORCE=true; shift ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            MISTAKE_FILE="$1"
            shift
            ;;
    esac
done

if [[ -z "$MISTAKE_FILE" ]]; then
    echo "Error: Mistake file required" >&2
    echo "Usage: integrate_pitfall.sh <mistake_file>" >&2
    exit 1
fi

if [[ ! -f "$MISTAKE_FILE" ]]; then
    echo "Error: File not found: $MISTAKE_FILE" >&2
    exit 1
fi

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

DIRECTORY=$(extract_field "$MISTAKE_FILE" '^\*\*Directory\*\*')
OPERATION=$(extract_field "$MISTAKE_FILE" '^\*\*Operation\*\*')
WHAT_HAPPENED=$(extract_section "$MISTAKE_FILE" "What Happened")
ROOT_CAUSE=$(extract_section "$MISTAKE_FILE" "Root Cause")
SUGGESTED_FIX=$(extract_section "$MISTAKE_FILE" "Suggested Fix")

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

# Generate pitfall entry
# Try to extract from Suggested Fix, otherwise generate from What Happened
PITFALL_TITLE=""
PITFALL_BODY=""

if [[ -n "$SUGGESTED_FIX" && "$SUGGESTED_FIX" != "_Awaiting analysis_" ]]; then
    # Try to extract a meaningful pitfall from the suggested fix
    PITFALL_TITLE=$(echo "$OPERATION" | sed 's/[^a-zA-Z0-9 ]//g' | head -c 50)
    PITFALL_BODY="$ROOT_CAUSE"
elif [[ -n "$ROOT_CAUSE" && "$ROOT_CAUSE" != "_Awaiting analysis_" ]]; then
    PITFALL_TITLE=$(echo "$OPERATION" | sed 's/[^a-zA-Z0-9 ]//g' | head -c 50)
    PITFALL_BODY="$ROOT_CAUSE"
else
    PITFALL_TITLE=$(echo "$OPERATION" | sed 's/[^a-zA-Z0-9 ]//g' | head -c 50)
    PITFALL_BODY="$WHAT_HAPPENED"
fi

# Clean up the pitfall
PITFALL_TITLE=$(echo "$PITFALL_TITLE" | sed 's/^ *//;s/ *$//')
PITFALL_BODY=$(echo "$PITFALL_BODY" | tr '\n' ' ' | sed 's/  */ /g;s/^ *//;s/ *$//' | head -c 200)

if [[ -z "$PITFALL_TITLE" ]]; then
    PITFALL_TITLE="Untitled pitfall"
fi

# Format the pitfall entry
PITFALL_ENTRY="### $PITFALL_TITLE

$PITFALL_BODY

_Source: $(basename "$MISTAKE_FILE")_"

echo ""
echo "Generated pitfall entry:"
echo "---"
echo "$PITFALL_ENTRY"
echo "---"
echo ""

# Check if similar pitfall already exists
if ! $FORCE; then
    if grep -qi "$(echo "$PITFALL_TITLE" | head -c 20)" "$COVERING_NODE" 2>/dev/null; then
        echo "Warning: Similar pitfall may already exist in $COVERING_NODE" >&2
        echo "Use --force to add anyway" >&2
        exit 2
    fi
fi

if $DRY_RUN; then
    echo "[DRY RUN] Would append pitfall to: $COVERING_NODE"
    echo "[DRY RUN] Would move $MISTAKE_FILE to integrated/"
    exit 0
fi

# Check if Pitfalls section exists
if ! grep -q '^## Pitfalls' "$COVERING_NODE"; then
    echo "Adding ## Pitfalls section to $COVERING_NODE"
    echo "" >> "$COVERING_NODE"
    echo "## Pitfalls" >> "$COVERING_NODE"
    echo "" >> "$COVERING_NODE"
fi

# Append pitfall entry after the ## Pitfalls header
# We write the pitfall to a temp file and use sed to insert it
TEMP_FILE=$(mktemp)
PITFALL_FILE=$(mktemp)

# Write pitfall to temp file (preserves newlines properly)
printf '%s\n\n' "$PITFALL_ENTRY" > "$PITFALL_FILE"

# Find the line number of "## Pitfalls"
PITFALL_LINE=$(grep -n '^## Pitfalls' "$COVERING_NODE" | head -1 | cut -d: -f1)

if [[ -z "$PITFALL_LINE" ]]; then
    echo "Error: Could not find ## Pitfalls section" >&2
    rm -f "$PITFALL_FILE"
    exit 1
fi

# Insert after the Pitfalls header (skip one blank line if present)
# Strategy: head to get lines up to and including header + 1, cat pitfall, tail for rest
NEXT_LINE=$((PITFALL_LINE + 1))
TOTAL_LINES=$(wc -l < "$COVERING_NODE" | tr -d ' ')

# Get everything up to the line after ## Pitfalls
head -n "$NEXT_LINE" "$COVERING_NODE" > "$TEMP_FILE"
# Add blank line if not already present
[[ $(tail -c 1 "$TEMP_FILE" | wc -l) -eq 0 ]] && echo "" >> "$TEMP_FILE"
# Add the pitfall
cat "$PITFALL_FILE" >> "$TEMP_FILE"
# Add the rest of the file (if any)
if [[ "$NEXT_LINE" -lt "$TOTAL_LINES" ]]; then
    tail -n "+$((NEXT_LINE + 1))" "$COVERING_NODE" >> "$TEMP_FILE"
fi

rm -f "$PITFALL_FILE"
mv "$TEMP_FILE" "$COVERING_NODE"
echo "✓ Pitfall added to $COVERING_NODE"

# Move mistake to integrated
MISTAKE_DIR=$(dirname "$MISTAKE_FILE")
INTEGRATED_DIR="${MISTAKE_DIR%/pending}/integrated"
mkdir -p "$INTEGRATED_DIR"

# Mark as integrated in the file
sed -i.bak 's/- \[ \] Pitfall added/- [x] Pitfall added/' "$MISTAKE_FILE" 2>/dev/null || \
    sed -i '' 's/- \[ \] Pitfall added/- [x] Pitfall added/' "$MISTAKE_FILE"
rm -f "$MISTAKE_FILE.bak"

mv "$MISTAKE_FILE" "$INTEGRATED_DIR/"
echo "✓ Moved to $INTEGRATED_DIR/"

echo ""
echo "Integration complete!"
