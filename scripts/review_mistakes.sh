#!/usr/bin/env bash
# Interactive review of pending mistake reports
# Usage: review_mistakes.sh [OPTIONS] [PATH]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"

show_help() {
    cat << 'EOF'
review_mistakes.sh - Interactive review of pending mistakes

USAGE:
    review_mistakes.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Project root (default: current directory)

OPTIONS:
    -h, --help           Show this help
    -a, --auto-integrate Auto-integrate on accept (default: prompt)
    -s, --skeletons-only Only review skeleton reports
    -q, --quiet          Less verbose output

INTERACTIVE COMMANDS:
    a, accept     Accept and integrate into AGENTS.md
    r, reject     Reject (move to rejected/)
    d, discard    Discard (delete skeleton, it was exploratory)
    e, edit       Open in $EDITOR for enrichment
    s, skip       Skip for now
    q, quit       Exit review

WORKFLOW:
    1. Run this script to review pending mistakes
    2. For each mistake, choose accept/reject/discard/edit/skip
    3. Accepted mistakes are auto-integrated into covering AGENTS.md
    4. Rejected mistakes are moved to rejected/ with reason
    5. Discarded skeletons are deleted (exploratory failures)

EXIT CODES:
    0    Review completed
    1    Error
EOF
    exit 0
}

PROJECT_ROOT="."
AUTO_INTEGRATE=false
SKELETONS_ONLY=false
QUIET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -a|--auto-integrate) AUTO_INTEGRATE=true; shift ;;
        -s|--skeletons-only) SKELETONS_ONLY=true; shift ;;
        -q|--quiet) QUIET=true; shift ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            PROJECT_ROOT="$1"
            shift
            ;;
    esac
done

PENDING_DIR="$PROJECT_ROOT/.intent-layer/mistakes/pending"
ACCEPTED_DIR="$PROJECT_ROOT/.intent-layer/mistakes/accepted"
REJECTED_DIR="$PROJECT_ROOT/.intent-layer/mistakes/rejected"
INTEGRATE_SCRIPT="$PLUGIN_ROOT/lib/integrate_pitfall.sh"

if [[ ! -d "$PENDING_DIR" ]]; then
    echo "No pending mistakes directory found at $PENDING_DIR"
    echo "Nothing to review."
    exit 0
fi

# Find pending files
if $SKELETONS_ONLY; then
    FILES=($(find "$PENDING_DIR" -name "SKELETON-*.md" -type f 2>/dev/null | sort))
else
    FILES=($(find "$PENDING_DIR" -name "*.md" -type f 2>/dev/null | sort))
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No pending mistakes to review."
    exit 0
fi

echo ""
echo "=== Intent Layer Mistake Review ==="
echo "Found ${#FILES[@]} pending report(s)"
echo ""
echo "Commands: [a]ccept [r]eject [d]iscard [e]dit [s]kip [q]uit"
echo ""

REVIEWED=0
ACCEPTED=0
REJECTED=0
DISCARDED=0
SKIPPED=0

for file in "${FILES[@]}"; do
    REVIEWED=$((REVIEWED + 1))
    FILENAME=$(basename "$file")

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[$REVIEWED/${#FILES[@]}] $FILENAME"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Show summary of the report
    if ! $QUIET; then
        # Extract key fields
        DIR=$(grep -m1 '^\*\*Directory\*\*' "$file" 2>/dev/null | sed 's/.*: //' || echo "?")
        OP=$(grep -m1 '^\*\*Operation\*\*' "$file" 2>/dev/null | sed 's/.*: //' || echo "?")
        STATUS=$(grep -m1 '^\*\*Status\*\*' "$file" 2>/dev/null | sed 's/.*: //' || echo "full")

        echo "Directory:  $DIR"
        echo "Operation:  $OP"
        echo "Status:     $STATUS"
        echo ""

        # Show What Happened section
        echo "What Happened:"
        awk '/^### What Happened/,/^### /' "$file" | grep -v '^### ' | head -5
        echo ""

        # Show Root Cause if not skeleton
        if [[ "$STATUS" != "skeleton"* ]]; then
            echo "Root Cause:"
            awk '/^### Root Cause/,/^### /' "$file" | grep -v '^### ' | head -3
            echo ""
        fi
    fi

    # Check for potential duplicates before showing options
    DUPLICATE_WARNING=""
    if [[ -x "$INTEGRATE_SCRIPT" ]]; then
        # Extract directory and operation for a temporary check
        CHECK_DIR=$(grep -m1 '^\*\*Directory\*\*' "$file" 2>/dev/null | sed 's/.*: //' || echo "")
        if [[ -n "$CHECK_DIR" && "$CHECK_DIR" != "unknown" ]]; then
            # Run check-only to see if duplicate exists
            DEDUP_CHECK=$("$INTEGRATE_SCRIPT" --check-only "$file" 2>&1 || true)
            if echo "$DEDUP_CHECK" | grep -q "POTENTIAL DUPLICATE"; then
                OVERLAP=$(echo "$DEDUP_CHECK" | grep "POTENTIAL DUPLICATE" | sed 's/.*(\([0-9]*\)%.*/\1/')
                EXISTING=$(echo "$DEDUP_CHECK" | grep "Existing entry title:" | sed 's/.*: //')
                DUPLICATE_WARNING="[!] Similar entry exists (${OVERLAP}% match): $EXISTING"
            fi
        fi
    fi

    # Show duplicate warning if found
    if [[ -n "$DUPLICATE_WARNING" ]]; then
        echo ""
        echo "  $DUPLICATE_WARNING"
        echo ""
    fi

    # Prompt for action
    while true; do
        read -r -p "Action [a/r/d/e/s/q/?]: " action
        action=$(echo "$action" | tr '[:upper:]' '[:lower:]')

        case "$action" in
            a|accept)
                mkdir -p "$ACCEPTED_DIR"

                if $AUTO_INTEGRATE && [[ -x "$INTEGRATE_SCRIPT" ]]; then
                    # Move to accepted first
                    mv "$file" "$ACCEPTED_DIR/"
                    ACCEPTED_FILE="$ACCEPTED_DIR/$FILENAME"

                    echo "Integrating pitfall..."
                    if "$INTEGRATE_SCRIPT" "$ACCEPTED_FILE"; then
                        echo "✓ Integrated successfully"
                    else
                        echo "⚠ Integration failed - file remains in accepted/"
                    fi
                else
                    mv "$file" "$ACCEPTED_DIR/"
                    echo "✓ Moved to accepted/"
                    echo "  Run: $INTEGRATE_SCRIPT $ACCEPTED_DIR/$FILENAME"
                fi

                ACCEPTED=$((ACCEPTED + 1))
                break
                ;;

            r|reject)
                read -r -p "Rejection reason: " reason
                reason=${reason:-"Not a real mistake"}

                mkdir -p "$REJECTED_DIR"

                # Add rejection reason to file
                echo "" >> "$file"
                echo "### Rejection" >> "$file"
                echo "**Reason**: $reason" >> "$file"
                echo "**Date**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$file"

                mv "$file" "$REJECTED_DIR/"
                echo "✓ Rejected: $reason"

                REJECTED=$((REJECTED + 1))
                break
                ;;

            d|discard)
                rm "$file"
                echo "✓ Discarded (deleted)"

                DISCARDED=$((DISCARDED + 1))
                break
                ;;

            e|edit)
                EDITOR=${EDITOR:-vim}
                "$EDITOR" "$file"
                echo "Edited. Re-showing for review..."
                ;;

            s|skip)
                echo "Skipped"
                SKIPPED=$((SKIPPED + 1))
                break
                ;;

            q|quit)
                echo ""
                echo "Exiting review early."
                break 2
                ;;

            "?"|help)
                echo ""
                echo "Commands:"
                echo "  a, accept  - Accept and integrate into AGENTS.md"
                echo "  r, reject  - Reject with reason (moves to rejected/)"
                echo "  d, discard - Delete skeleton (it was exploratory)"
                echo "  e, edit    - Open in \$EDITOR for enrichment"
                echo "  s, skip    - Skip for now"
                echo "  q, quit    - Exit review"
                echo ""
                ;;

            *)
                echo "Unknown command. Type '?' for help."
                ;;
        esac
    done

    echo ""
done

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Review Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Reviewed:  $REVIEWED"
echo "  Accepted:  $ACCEPTED"
echo "  Rejected:  $REJECTED"
echo "  Discarded: $DISCARDED"
echo "  Skipped:   $SKIPPED"
echo ""

REMAINING=$(find "$PENDING_DIR" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
if [[ "$REMAINING" -gt 0 ]]; then
    echo "$REMAINING report(s) still pending."
fi
