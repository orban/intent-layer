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
            if [[ -z "${2:-}" ]]; then
                echo "Error: --pr requires a NUMBER argument" >&2
                exit 1
            fi
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
            if [[ -z "${2:-}" ]]; then
                echo "Error: --output requires a FILE argument" >&2
                exit 1
            fi
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

# Validate git repository
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Error: Not in a git repository" >&2
    exit 1
}
cd "$REPO_ROOT"

# Validate refs
if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $BASE_REF" >&2
    exit 1
fi
if ! git rev-parse --verify "$HEAD_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $HEAD_REF" >&2
    exit 1
fi

# Get changed files
CHANGED_FILES=$(git diff --name-only "$BASE_REF" "$HEAD_REF" 2>/dev/null) || {
    echo "Error: Failed to get diff" >&2
    exit 1
}

if [ -z "$CHANGED_FILES" ]; then
    echo "No changed files detected."
    exit 0
fi

FILE_COUNT=$(echo "$CHANGED_FILES" | grep -v '^$' | wc -l | tr -d ' ')
echo "Changed files: $FILE_COUNT"

# Find covering Intent Node for a file
find_covering_node() {
    local file="$1"
    local dir=$(dirname "$file")

    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
        if [ -f "$dir/AGENTS.md" ]; then
            echo "$dir/AGENTS.md"
            return
        fi
        if [ -f "$dir/CLAUDE.md" ]; then
            echo "$dir/CLAUDE.md"
            return
        fi
        dir=$(dirname "$dir")
    done

    # Check root
    if [ -f "AGENTS.md" ]; then
        echo "AGENTS.md"
    elif [ -f "CLAUDE.md" ]; then
        echo "CLAUDE.md"
    fi
}

# Map changed files to covering nodes
declare -A NODE_FILES
declare -A NODE_CONTENT

while IFS= read -r file; do
    [ -z "$file" ] && continue
    [[ "$file" == *"AGENTS.md" ]] || [[ "$file" == *"CLAUDE.md" ]] && continue

    node=$(find_covering_node "$file")
    if [ -n "$node" ]; then
        if [ -z "${NODE_FILES[$node]:-}" ]; then
            NODE_FILES[$node]="$file"
            NODE_CONTENT[$node]=$(cat "$node" 2>/dev/null || echo "")
        else
            NODE_FILES[$node]="${NODE_FILES[$node]}"$'\n'"$file"
        fi
    fi
done <<< "$CHANGED_FILES"

AFFECTED_NODE_COUNT=${#NODE_FILES[@]}
echo "Affected Intent Nodes: $AFFECTED_NODE_COUNT"

# Semantic signal patterns
SECURITY_PATTERNS="auth|password|token|secret|permission|encrypt|credential|login|session"
DATA_PATTERNS="migration|schema|DELETE|DROP|transaction|database|sql|query"
API_PATTERNS="/api/|endpoint|route|breaking|deprecated|version"

# Calculate risk score
calculate_risk_score() {
    local score=0
    local factors=""

    # Files changed: 1 point per 5 files
    local file_points=$((FILE_COUNT / 5))
    if [ $file_points -gt 0 ]; then
        score=$((score + file_points))
        factors="${factors}Files changed: +${file_points}\n"
    fi

    # Count contracts and pitfalls in affected nodes
    local contract_count=0
    local pitfall_count=0
    local critical_count=0

    for node in "${!NODE_CONTENT[@]}"; do
        local content="${NODE_CONTENT[$node]}"

        # Count items in Contracts section
        local in_contracts
        in_contracts=$(echo "$content" | grep -c -iE "^- .*(must|never|always|require)" 2>/dev/null || true)
        in_contracts=${in_contracts:-0}
        in_contracts=$(echo "$in_contracts" | tr -d '[:space:]')
        contract_count=$((contract_count + in_contracts))

        # Count items in Pitfalls section
        local in_pitfalls
        in_pitfalls=$(echo "$content" | grep -c -iE "^- .*(pitfall|silently|unexpected|surprising)" 2>/dev/null || true)
        in_pitfalls=${in_pitfalls:-0}
        in_pitfalls=$(echo "$in_pitfalls" | tr -d '[:space:]')
        pitfall_count=$((pitfall_count + in_pitfalls))

        # Count critical items
        local critical
        critical=$(echo "$content" | grep -c -E "^- (⚠️|CRITICAL:)" 2>/dev/null || true)
        critical=${critical:-0}
        critical=$(echo "$critical" | tr -d '[:space:]')
        critical_count=$((critical_count + critical))
    done

    # Contracts: 2 points each
    if [ $contract_count -gt 0 ]; then
        local contract_points=$((contract_count * 2))
        score=$((score + contract_points))
        factors="${factors}Contracts ($contract_count): +${contract_points}\n"
    fi

    # Pitfalls: 3 points each
    if [ $pitfall_count -gt 0 ]; then
        local pitfall_points=$((pitfall_count * 3))
        score=$((score + pitfall_points))
        factors="${factors}Pitfalls ($pitfall_count): +${pitfall_points}\n"
    fi

    # Critical items: 5 points each
    if [ $critical_count -gt 0 ]; then
        local critical_points=$((critical_count * 5))
        score=$((score + critical_points))
        factors="${factors}Critical items ($critical_count): +${critical_points}\n"
    fi

    # Semantic signals in changed files
    local diff_content=$(git diff "$BASE_REF" "$HEAD_REF" 2>/dev/null || echo "")

    if echo "$diff_content" | grep -qiE "$SECURITY_PATTERNS"; then
        score=$((score + 10))
        factors="${factors}Security patterns: +10\n"
    fi

    if echo "$diff_content" | grep -qiE "$DATA_PATTERNS"; then
        score=$((score + 10))
        factors="${factors}Data patterns: +10\n"
    fi

    if echo "$diff_content" | grep -qiE "$API_PATTERNS"; then
        score=$((score + 5))
        factors="${factors}API patterns: +5\n"
    fi

    # Output
    RISK_SCORE=$score
    RISK_FACTORS="$factors"

    if [ $score -le 15 ]; then
        RISK_LEVEL="Low"
    elif [ $score -le 35 ]; then
        RISK_LEVEL="Medium"
    else
        RISK_LEVEL="High"
    fi
}

calculate_risk_score

echo "PR Review Mode - review_pr.sh v$VERSION"
echo "Comparing: $BASE_REF..$HEAD_REF"
