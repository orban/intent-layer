#!/usr/bin/env bash
# Mine GitHub PR reviews for Intent Layer insights
# Usage: ./mine_pr_reviews.sh [OPTIONS]

set -euo pipefail

show_help() {
    cat << 'EOF'
mine_pr_reviews.sh - Extract Intent Layer content from GitHub PRs

USAGE:
    mine_pr_reviews.sh [OPTIONS]

OPTIONS:
    -h, --help           Show this help message
    -s, --since DATE     Analyze PRs merged since DATE (ISO format: YYYY-MM-DD)
    -l, --limit N        Limit to N most recent PRs (default: 50)
    -q, --quiet          Output only findings, no headers
    --skip-comments      Skip fetching review comments (faster)

REQUIREMENTS:
    - GitHub CLI (gh) installed and authenticated
    - jq installed for JSON parsing
    - Current directory must be a GitHub repository

PR SECTIONS PARSED:
    ## Breaking Changes  -> Contracts
    ## Why/Motivation    -> Architecture Decisions
    ## Risks/Concerns    -> Pitfalls
    ## Alternatives      -> Anti-patterns

KEYWORD FALLBACK:
    don't, never, avoid, careful     -> Pitfalls
    must, always, required           -> Contracts

OUTPUT:
    Markdown tables with columns: PR | Finding | Source | Confidence

EXAMPLES:
    mine_pr_reviews.sh                      # Last 50 merged PRs
    mine_pr_reviews.sh --since 2024-06-01   # PRs merged since date
    mine_pr_reviews.sh --limit 100          # Last 100 merged PRs
    mine_pr_reviews.sh --skip-comments      # Faster, PR bodies only

EXIT CODES:
    0    Success (findings may be empty)
    1    Error (gh not installed, not authenticated, not GitHub repo)
EOF
    exit 0
}

# Defaults
SINCE=""
LIMIT=50
QUIET=false
SKIP_COMMENTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -s|--since)
            SINCE="$2"
            shift 2
            ;;
        -l|--limit)
            LIMIT="$2"
            shift 2
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        --skip-comments)
            SKIP_COMMENTS=true
            shift
            ;;
        -*)
            echo "❌ Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            echo "❌ Error: Unexpected argument: $1" >&2
            echo "   This script operates on the current repository." >&2
            exit 1
            ;;
    esac
done

# Check gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI (gh) not found" >&2
    echo "" >&2
    echo "   Install: https://cli.github.com/" >&2
    echo "   macOS: brew install gh" >&2
    exit 1
fi

# Check gh is authenticated
if ! gh auth status &> /dev/null 2>&1; then
    echo "❌ Error: GitHub CLI not authenticated" >&2
    echo "" >&2
    echo "   Run: gh auth login" >&2
    exit 1
fi

# Check jq is installed
if ! command -v jq &> /dev/null; then
    echo "❌ Error: jq not found" >&2
    echo "" >&2
    echo "   Install jq for JSON parsing" >&2
    echo "   macOS: brew install jq" >&2
    exit 1
fi

# Check we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: Not a git repository" >&2
    exit 1
fi

# Get repository name
REPO_NAME=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null) || {
    echo "❌ Error: Could not determine repository" >&2
    echo "" >&2
    echo "   Make sure this is a GitHub repository." >&2
    exit 1
}

# Arrays to store findings
declare -a PITFALLS=()
declare -a ANTIPATTERNS=()
declare -a DECISIONS=()
declare -a CONTRACTS=()

# Escape pipes for markdown tables
escape_pipes() {
    local text="$1"
    echo "${text//|/\\|}"
}

# Truncate text to max length
truncate_text() {
    local text="$1"
    local max_len="${2:-80}"

    # Remove newlines and excess whitespace
    text=$(echo "$text" | tr '\n' ' ' | tr -s ' ' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')

    if [ ${#text} -gt "$max_len" ]; then
        echo "${text:0:$max_len}..."
    else
        echo "$text"
    fi
}

# Extract section content from PR body using awk
extract_section() {
    local body="$1"
    local pattern="$2"

    echo "$body" | awk -v pat="$pattern" '
        BEGIN { found=0; IGNORECASE=1 }
        $0 ~ pat { found=1; next }
        found && /^##[^#]/ { found=0 }
        found { print }
    ' | head -10
}

# Check for warning keywords (pitfalls)
has_warning_keywords() {
    local text="$1"
    echo "$text" | grep -qiE "(don'?t|never|avoid|careful|watch out|beware)"
}

# Check for requirement keywords (contracts)
has_requirement_keywords() {
    local text="$1"
    echo "$text" | grep -qiE "(must|always|required|invariant|shall)"
}

# Process a single PR
process_pr() {
    local number="$1"
    local body="$2"

    [ -z "$body" ] || [ "$body" = "null" ] && return

    local found_section=false

    # Breaking Changes -> Contracts
    local breaking
    breaking=$(extract_section "$body" "^##[[:space:]]*(Breaking|BREAKING)")
    if [ -n "$breaking" ]; then
        local finding
        finding=$(truncate_text "$breaking" 80)
        finding=$(escape_pipes "$finding")
        CONTRACTS+=("#$number|$finding|PR body (Breaking)|High")
        found_section=true
    fi

    # Check for BREAKING CHANGE: inline
    if echo "$body" | grep -qi "BREAKING CHANGE:"; then
        local line
        line=$(echo "$body" | grep -i "BREAKING CHANGE:" | head -1)
        local finding
        finding=$(truncate_text "$line" 80)
        finding=$(escape_pipes "$finding")
        CONTRACTS+=("#$number|$finding|PR body (Breaking)|High")
        found_section=true
    fi

    # Why/Motivation -> Architecture Decisions
    local motivation
    motivation=$(extract_section "$body" "^##[[:space:]]*(Why|Motivation|Rationale)")
    if [ -n "$motivation" ]; then
        local finding
        finding=$(truncate_text "$motivation" 80)
        finding=$(escape_pipes "$finding")
        DECISIONS+=("#$number|$finding|PR body (Why)|High")
        found_section=true
    fi

    # Risks/Concerns -> Pitfalls
    local risks
    risks=$(extract_section "$body" "^##[[:space:]]*(Risks?|Concerns?|Caveats?)")
    if [ -n "$risks" ]; then
        local finding
        finding=$(truncate_text "$risks" 80)
        finding=$(escape_pipes "$finding")
        PITFALLS+=("#$number|$finding|PR body (Risks)|High")
        found_section=true
    fi

    # Alternatives -> Anti-patterns
    local alternatives
    alternatives=$(extract_section "$body" "^##[[:space:]]*(Alternatives)")
    if [ -n "$alternatives" ]; then
        local finding
        finding=$(truncate_text "$alternatives" 80)
        finding=$(escape_pipes "$finding")
        ANTIPATTERNS+=("#$number|$finding|PR body (Alternatives)|High")
        found_section=true
    fi

    # Keyword fallback if no sections found
    if [ "$found_section" = false ]; then
        if has_warning_keywords "$body"; then
            local line
            line=$(echo "$body" | grep -iE "(don'?t|never|avoid|careful|watch out|beware)" | head -1)
            if [ -n "$line" ]; then
                local finding
                finding=$(truncate_text "$line" 80)
                finding=$(escape_pipes "$finding")
                PITFALLS+=("#$number|$finding|PR body (keyword)|Medium")
            fi
        fi

        if has_requirement_keywords "$body"; then
            local line
            line=$(echo "$body" | grep -iE "(must|always|required|invariant|shall)" | head -1)
            if [ -n "$line" ]; then
                local finding
                finding=$(truncate_text "$line" 80)
                finding=$(escape_pipes "$finding")
                CONTRACTS+=("#$number|$finding|PR body (keyword)|Medium")
            fi
        fi
    fi
}

# Process review comments for a PR
process_comments() {
    local pr_number="$1"

    local comments
    comments=$(gh api "repos/$REPO_NAME/pulls/$pr_number/comments" --jq '.[].body' 2>/dev/null || echo "")

    [ -z "$comments" ] && return

    while IFS= read -r comment; do
        [ -z "$comment" ] && continue

        if has_warning_keywords "$comment"; then
            local finding
            finding=$(truncate_text "$comment" 80)
            finding=$(escape_pipes "$finding")
            PITFALLS+=("#$pr_number|$finding|Review comment|Medium")
        fi
    done <<< "$comments"
}

# Output markdown table
output_table() {
    local title="$1"
    shift
    local findings=("$@")

    [ ${#findings[@]} -eq 0 ] && return

    echo ""
    echo "### $title"
    echo ""
    echo "| PR | Finding | Source | Confidence |"
    echo "|----|---------|--------|------------|"

    for finding in "${findings[@]}"; do
        IFS='|' read -r pr text source confidence <<< "$finding"
        echo "| $pr | $text | $source | $confidence |"
    done
}

# Main execution
if [ "$QUIET" = false ]; then
    echo "## PR Review Mining Findings"
    echo ""
    echo "Repository: $REPO_NAME"
    echo "Limit: $LIMIT PRs"
    [ -n "$SINCE" ] && echo "Since: $SINCE"
    [ "$SKIP_COMMENTS" = true ] && echo "Note: Review comments skipped"
    echo ""
fi

# Fetch PRs
PRS_JSON=$(gh pr list --state merged --limit "$LIMIT" --json number,title,body,mergedAt 2>/dev/null) || {
    echo "❌ Error: Failed to fetch PRs" >&2
    exit 1
}

# Filter by date if --since specified
if [ -n "$SINCE" ]; then
    PRS_JSON=$(echo "$PRS_JSON" | jq --arg since "$SINCE" '[.[] | select(.mergedAt >= $since)]')
fi

PR_COUNT=$(echo "$PRS_JSON" | jq 'length')

if [ "$PR_COUNT" -eq 0 ]; then
    if [ "$QUIET" = false ]; then
        echo "No merged PRs found."
        [ -n "$SINCE" ] && echo "Try adjusting --since or --limit."
    fi
    exit 0
fi

if [ "$QUIET" = false ]; then
    echo "Analyzing $PR_COUNT merged PRs..."
    echo ""
fi

# Process each PR
for i in $(seq 0 $((PR_COUNT - 1))); do
    number=$(echo "$PRS_JSON" | jq -r ".[$i].number")
    body=$(echo "$PRS_JSON" | jq -r ".[$i].body // empty")

    process_pr "$number" "$body"

    if [ "$SKIP_COMMENTS" = false ]; then
        process_comments "$number"
    fi
done

# Calculate totals
total_findings=$((${#PITFALLS[@]} + ${#ANTIPATTERNS[@]} + ${#DECISIONS[@]} + ${#CONTRACTS[@]}))

if [ "$total_findings" -eq 0 ]; then
    if [ "$QUIET" = false ]; then
        echo "No findings from PR reviews."
        echo ""
        echo "This could mean:"
        echo "- PRs don't use structured sections (## Breaking, ## Why, etc.)"
        echo "- PR descriptions are minimal"
        echo "- Try mine_git_history.sh for commit-level insights"
    fi
    exit 0
fi

# Output findings
output_table "Potential Pitfalls (from PR discussions)" "${PITFALLS[@]+"${PITFALLS[@]}"}"
output_table "Potential Anti-patterns (from rejected approaches)" "${ANTIPATTERNS[@]+"${ANTIPATTERNS[@]}"}"
output_table "Potential Architecture Decisions (from PR rationale)" "${DECISIONS[@]+"${DECISIONS[@]}"}"
output_table "Potential Contracts (from breaking changes)" "${CONTRACTS[@]+"${CONTRACTS[@]}"}"

echo ""
echo "---"
echo ""
echo "**Review needed**: Human should verify findings before adding to AGENTS.md."
echo "Total findings: $total_findings from $PR_COUNT PRs"
