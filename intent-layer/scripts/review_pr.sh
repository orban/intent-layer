#!/usr/bin/env bash
# Review a PR against the Intent Layer
# Usage: ./review_pr.sh [OPTIONS] [BASE_REF] [HEAD_REF]

set -euo pipefail

VERSION="1.0.0"

show_help() {
    cat << 'EOF'
review_pr.sh - Review PR against Intent Layer

USAGE:
    review_pr.sh [OPTIONS] [BASE_REF] [HEAD_REF]

ARGUMENTS:
    BASE_REF    Git ref to compare from (default: origin/main)
    HEAD_REF    Git ref to compare to (default: HEAD)

OPTIONS:
    -h, --help          Show this help message
    -v, --version       Show version
    --pr NUMBER         Fetch GitHub PR metadata (requires gh CLI)
    --ai-generated      Enable AI-generated code checks
    --summary           Output Layer 1 only (risk score)
    --checklist         Output Layers 1+2 (score + checklist)
    --full              Output all layers (default)
    --exit-code         Exit with code based on risk level (0=low, 1=medium, 2=high)
    --output FILE       Write output to file instead of stdout

EXAMPLES:
    review_pr.sh main HEAD
    review_pr.sh main HEAD --pr 123 --ai-generated
    review_pr.sh --summary
    review_pr.sh main HEAD --exit-code
EOF
    exit 0
}

show_version() {
    echo "review_pr.sh version $VERSION"
    exit 0
}

# Defaults
BASE_REF=""
HEAD_REF="HEAD"
PR_NUMBER=""
AI_GENERATED=false
OUTPUT_MODE="full"
EXIT_CODE_MODE=false
OUTPUT_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -v|--version)
            show_version
            ;;
        --pr)
            PR_NUMBER="$2"
            shift 2
            ;;
        --ai-generated)
            AI_GENERATED=true
            shift
            ;;
        --summary)
            OUTPUT_MODE="summary"
            shift
            ;;
        --checklist)
            OUTPUT_MODE="checklist"
            shift
            ;;
        --full)
            OUTPUT_MODE="full"
            shift
            ;;
        --exit-code)
            EXIT_CODE_MODE=true
            shift
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [ -z "$BASE_REF" ]; then
                BASE_REF="$1"
            elif [ "$HEAD_REF" = "HEAD" ]; then
                HEAD_REF="$1"
            else
                echo "Error: Too many arguments" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Default base ref
if [ -z "$BASE_REF" ]; then
    BASE_REF="origin/main"
fi

echo "PR Review Mode - review_pr.sh v$VERSION"
echo "Comparing: $BASE_REF..$HEAD_REF"
