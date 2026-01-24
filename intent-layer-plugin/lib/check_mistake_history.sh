#!/usr/bin/env bash
# Check if a directory has a history of mistakes
# Usage: check_mistake_history.sh <directory> [--threshold N]

set -euo pipefail

show_help() {
    cat << 'EOF'
check_mistake_history.sh - Check directory mistake history

USAGE:
    check_mistake_history.sh <directory> [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -t, --threshold N    Mistake count for "high risk" (default: 2)
    --json               Output as JSON

EXIT CODES:
    0    High-risk (count >= threshold)
    1    Low-risk (count < threshold)
EOF
    exit 0
}

# Escape regex special chars: . * [ ] ^ $ \ + ? { } | ( )
escape_regex() {
    printf '%s\n' "$1" | sed 's/[].[*^$()+?{|\\]/\\&/g'
}

DIRECTORY=""
THRESHOLD=2
JSON_OUTPUT=false
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -t|--threshold)
            THRESHOLD="$2"
            shift 2
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        *)
            if [[ -z "$DIRECTORY" ]]; then
                DIRECTORY="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$DIRECTORY" ]]; then
    echo "Error: Directory path required" >&2
    exit 1
fi

# Validate threshold is a positive integer
if ! [[ "$THRESHOLD" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --threshold requires a positive integer (got: $THRESHOLD)" >&2
    exit 1
fi

# Normalize directory path (remove trailing slash)
DIRECTORY="${DIRECTORY%/}"

# Convert to relative path for matching
REL_DIR="${DIRECTORY#$PROJECT_ROOT/}"

# Handle case where directory equals project root
if [[ "$REL_DIR" == "$DIRECTORY" && "$DIRECTORY" == "." ]]; then
    REL_DIR="."
fi

COUNT=0

# Check both pending and accepted directories
for subdir in pending accepted; do
    mistakes_path="$PROJECT_ROOT/.intent-layer/mistakes/$subdir"

    # Gracefully handle non-existent directories
    if [[ ! -d "$mistakes_path" ]]; then
        continue
    fi

    # Check if any .md files exist before attempting grep
    if ! ls "$mistakes_path"/*.md &>/dev/null; then
        continue
    fi

    # Count matches (grep -l lists files with matches)
    # Use quotes around path to handle spaces
    # Escape regex metacharacters in directory path
    ESCAPED_REL_DIR=$(escape_regex "$REL_DIR")
    matches=$(grep -l "^\*\*Directory\*\*:.*$ESCAPED_REL_DIR" "$mistakes_path"/*.md 2>/dev/null | wc -l || echo 0)
    # Trim whitespace from wc output (macOS adds leading spaces)
    matches=$(echo "$matches" | tr -d ' ')
    COUNT=$((COUNT + matches))
done

HIGH_RISK=false
if [[ "$COUNT" -ge "$THRESHOLD" ]]; then
    HIGH_RISK=true
fi

if [[ "$JSON_OUTPUT" == true ]]; then
    if command -v jq &>/dev/null; then
        jq -n \
            --arg dir "$DIRECTORY" \
            --argjson count "$COUNT" \
            --argjson high_risk "$([[ $HIGH_RISK == true ]] && echo true || echo false)" \
            '{directory: $dir, count: $count, high_risk: $high_risk}'
    else
        # Fallback: escape quotes manually
        ESC_DIR="${DIRECTORY//\"/\\\"}"
        echo "{\"directory\": \"$ESC_DIR\", \"count\": $COUNT, \"high_risk\": $HIGH_RISK}"
    fi
fi

# Exit 0 for high-risk, 1 for low-risk
$HIGH_RISK && exit 0 || exit 1
