#!/usr/bin/env bash
# Aggregate recent learnings from accepted mistakes
# Usage: aggregate_learnings.sh [--days N] [--format summary|full]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

show_help() {
    cat << 'EOF'
aggregate_learnings.sh - Aggregate recent learnings for session injection

USAGE:
    aggregate_learnings.sh [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -d, --days N         Include learnings from last N days (default: 7)
    -f, --format FORMAT  Output format: summary|full (default: summary)
    -p, --path DIR       Project root to search (default: cwd or CLAUDE_PROJECT_DIR)

OUTPUT:
    Markdown summary of recent accepted mistakes. Empty if none found.
EOF
    exit 0
}

DAYS=7
FORMAT="summary"
PROJECT_PATH="${CLAUDE_PROJECT_DIR:-.}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -d|--days) DAYS="$2"; shift 2 ;;
        -f|--format) FORMAT="$2"; shift 2 ;;
        -p|--path) PROJECT_PATH="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
    echo "Error: --days requires a positive integer" >&2
    exit 1
fi

if [[ "$FORMAT" != "summary" && "$FORMAT" != "full" ]]; then
    echo "Error: --format must be 'summary' or 'full'" >&2
    exit 1
fi

MISTAKES_DIR="$PROJECT_PATH/.intent-layer/mistakes/accepted"

if [[ ! -d "$MISTAKES_DIR" ]]; then
    exit 0
fi

CUTOFF=$(date_days_ago "$DAYS")

RECENT_FILES=()
while IFS= read -r -d '' file; do
    if file_newer_than "$file" "$CUTOFF"; then
        RECENT_FILES+=("$file")
    fi
done < <(find "$MISTAKES_DIR" -name "MISTAKE-*.md" -type f -print0 2>/dev/null)

if [[ ${#RECENT_FILES[@]} -eq 0 ]]; then
    exit 0
fi

echo "## Recent Learnings (last $DAYS days)"
echo ""
echo "${#RECENT_FILES[@]} accepted mistake(s) converted to Intent Layer updates."
echo ""

if [[ "$FORMAT" == "full" ]]; then
    for file in "${RECENT_FILES[@]}"; do
        echo "---"
        echo ""
        cat "$file"
        echo ""
    done
else
    echo "| Directory | Root Cause | Fix Applied |"
    echo "|-----------|------------|-------------|"

    for file in "${RECENT_FILES[@]}"; do
        DIR=$(grep -m1 '^\*\*Directory\*\*:' "$file" 2>/dev/null | sed 's/.*: //' | head -c 30 || echo "?")
        CAUSE=$(grep -m1 '^### Root Cause' -A1 "$file" 2>/dev/null | tail -1 | head -c 40 || echo "?")
        DISP=$(grep -E '^\- \[x\]' "$file" 2>/dev/null | head -1 | sed 's/.*\] //' | head -c 25 || echo "?")
        echo "| $DIR | $CAUSE... | $DISP |"
    done
fi
