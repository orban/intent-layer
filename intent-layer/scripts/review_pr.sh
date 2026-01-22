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

# Fetch PR metadata if --pr flag used
PR_TITLE=""
PR_BODY=""
PR_AUTHOR=""

if [ -n "$PR_NUMBER" ]; then
    if ! command -v gh &> /dev/null; then
        echo "Warning: gh CLI not found, skipping PR metadata" >&2
    else
        PR_TITLE=$(gh pr view "$PR_NUMBER" --json title -q '.title' 2>/dev/null || echo "")
        PR_BODY=$(gh pr view "$PR_NUMBER" --json body -q '.body' 2>/dev/null || echo "")
        PR_AUTHOR=$(gh pr view "$PR_NUMBER" --json author -q '.author.login' 2>/dev/null || echo "")

        if [ -n "$PR_TITLE" ]; then
            echo "PR #${PR_NUMBER}: ${PR_TITLE}"
            echo "Author: ${PR_AUTHOR}"
        fi
    fi
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

# Extract checklist items from nodes
generate_checklist() {
    CRITICAL_ITEMS=""
    RELEVANT_ITEMS=""
    PITFALL_ITEMS=""

    for node in "${!NODE_CONTENT[@]}"; do
        local content="${NODE_CONTENT[$node]}"
        local files="${NODE_FILES[$node]}"

        # Extract critical items (always include)
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            CRITICAL_ITEMS="${CRITICAL_ITEMS}- [ ] ${line} (${node})\n"
        done < <(echo "$content" | grep -E "^- (⚠️|CRITICAL:)" | sed 's/^- //' || true)

        # Extract contracts that match changed file keywords
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            # Check if any changed file keyword appears in the contract
            local is_relevant=false
            while IFS= read -r file; do
                [ -z "$file" ] && continue
                local filename=$(basename "$file" | sed 's/\.[^.]*$//')
                if echo "$line" | grep -qi "$filename"; then
                    is_relevant=true
                    RELEVANT_ITEMS="${RELEVANT_ITEMS}- [ ] ${line} (${node})\n      Changed: ${file}\n"
                    break
                fi
            done <<< "$files"
        done < <(echo "$content" | grep -E "^- .*(must|never|always|require)" | grep -vE "^- (⚠️|CRITICAL:)" | sed 's/^- //' || true)

        # Extract pitfalls
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            PITFALL_ITEMS="${PITFALL_ITEMS}- [ ] ${line} (${node})\n"
        done < <(echo "$content" | grep -iE "^- .*(pitfall|silently|unexpected|surprising)" | sed 's/^- //' || true)
    done
}

generate_checklist

# AI-generated code specific checks
run_ai_checks() {
    [ "$AI_GENERATED" = false ] && return

    AI_DRIFT_WARNINGS=""
    AI_OVERENGINEERING=""
    AI_PATTERN_ISSUES=""
    AI_PITFALL_ALERTS=""

    local diff_content=$(git diff "$BASE_REF" "$HEAD_REF" 2>/dev/null || echo "")

    # Over-engineering detection
    # New files in utils/helpers/common
    local new_files=$(git diff --name-only --diff-filter=A "$BASE_REF" "$HEAD_REF" 2>/dev/null || echo "")
    while IFS= read -r file; do
        [ -z "$file" ] && continue
        if [[ "$file" == *"/utils/"* ]] || [[ "$file" == *"/helpers/"* ]] || [[ "$file" == *"/common/"* ]]; then
            AI_OVERENGINEERING="${AI_OVERENGINEERING}- New abstraction: ${file}\n  Is this necessary or could existing patterns handle it?\n"
        fi
    done <<< "$new_files"

    # Excessive try/catch (more than 3 new try blocks)
    local try_count
    try_count=$(echo "$diff_content" | grep -c "^+.*try {" || echo "0")
    try_count=$(echo "$try_count" | tr -d '[:space:]')
    if [ "$try_count" -gt 3 ]; then
        AI_OVERENGINEERING="${AI_OVERENGINEERING}- Excessive error handling: ${try_count} new try/catch blocks\n  Check if all error handling adds value\n"
    fi

    # New interfaces with single implementation pattern
    local new_interfaces
    new_interfaces=$(echo "$diff_content" | grep -c "^+.*interface " || echo "0")
    new_interfaces=$(echo "$new_interfaces" | tr -d '[:space:]')
    if [ "$new_interfaces" -gt 2 ]; then
        AI_OVERENGINEERING="${AI_OVERENGINEERING}- Multiple new interfaces: ${new_interfaces}\n  Verify these aren't premature abstractions\n"
    fi

    # Pitfall proximity - check if changes touch files near documented pitfalls
    for node in "${!NODE_CONTENT[@]}"; do
        local content="${NODE_CONTENT[$node]}"
        local files="${NODE_FILES[$node]}"
        local node_dir=$(dirname "$node")

        # Extract pitfalls
        while IFS= read -r pitfall; do
            [ -z "$pitfall" ] && continue
            AI_PITFALL_ALERTS="${AI_PITFALL_ALERTS}- ${node_dir}: ${pitfall}\n  Verify: Does new code handle this edge case?\n"
        done < <(echo "$content" | grep -iE "^- .*(silently|fails|unexpected)" | sed 's/^- //' | head -3 || true)
    done

    # Intent drift detection (when PR metadata available)
    if [ -n "$PR_TITLE" ] || [ -n "$PR_BODY" ]; then
        local pr_text="${PR_TITLE} ${PR_BODY}"

        for node in "${!NODE_CONTENT[@]}"; do
            local content="${NODE_CONTENT[$node]}"

            # Check for conflicting approaches
            # JWT vs session tokens
            if echo "$pr_text" | grep -qi "jwt" && echo "$content" | grep -qi "session.*not.*jwt\|no.*jwt"; then
                AI_DRIFT_WARNINGS="${AI_DRIFT_WARNINGS}- PR mentions JWT but ${node} says: avoid JWT\n"
            fi

            # Check architecture decisions
            while IFS= read -r decision; do
                [ -z "$decision" ] && continue
                # Extract the "don't do X" patterns
                local avoid=$(echo "$decision" | grep -oiE "not|avoid|never|don't" || echo "")
                if [ -n "$avoid" ]; then
                    local pattern=$(echo "$decision" | grep -oiE "[a-zA-Z]+" | head -3 | tr '\n' '|' | sed 's/|$//')
                    if echo "$pr_text" | grep -qiE "$pattern"; then
                        AI_DRIFT_WARNINGS="${AI_DRIFT_WARNINGS}- Potential conflict: PR may contradict: ${decision}\n"
                    fi
                fi
            done < <(echo "$content" | grep -iE "^- .*(architecture|decision|approach)" | head -5 || true)
        done
    fi
}

run_ai_checks

# Generate output
generate_output() {
    local output=""

    # Layer 1: Risk Summary
    output+="# PR Review Summary\n\n"
    output+="## Risk Assessment\n\n"
    output+="**Score: ${RISK_SCORE} (${RISK_LEVEL})**\n\n"
    output+="Contributing factors:\n"
    output+="${RISK_FACTORS}\n"

    case $RISK_LEVEL in
        "Low")
            output+="Recommendation: Standard review\n\n"
            ;;
        "Medium")
            output+="Recommendation: Careful review recommended\n\n"
            ;;
        "High")
            output+="Recommendation: Thorough review required\n\n"
            ;;
    esac

    [ "$OUTPUT_MODE" = "summary" ] && { echo -e "$output"; return; }

    # Layer 2: Checklist
    output+="---\n\n"
    output+="## Review Checklist\n\n"

    if [ -n "$CRITICAL_ITEMS" ]; then
        output+="### Critical (always verify)\n\n"
        output+="${CRITICAL_ITEMS}\n"
    fi

    if [ -n "$RELEVANT_ITEMS" ]; then
        output+="### Relevant to this PR\n\n"
        output+="${RELEVANT_ITEMS}\n"
    fi

    if [ -n "$PITFALL_ITEMS" ]; then
        output+="### Pitfalls in affected areas\n\n"
        output+="${PITFALL_ITEMS}\n"
    fi

    # AI-specific sections
    if [ "$AI_GENERATED" = true ]; then
        output+="---\n\n"
        output+="## AI-Generated Code Checks\n\n"

        if [ -n "$AI_OVERENGINEERING" ]; then
            output+="### Complexity Check\n\n"
            output+="Potential over-engineering detected:\n\n"
            output+="${AI_OVERENGINEERING}\n"
        fi

        if [ -n "$AI_PITFALL_ALERTS" ]; then
            output+="### Pitfall Proximity Alerts\n\n"
            output+="AI modified code adjacent to known sharp edges:\n\n"
            output+="${AI_PITFALL_ALERTS}\n"
        fi

        if [ -n "$AI_DRIFT_WARNINGS" ]; then
            output+="### Intent Drift Warnings\n\n"
            output+="${AI_DRIFT_WARNINGS}\n"
        fi
    fi

    [ "$OUTPUT_MODE" = "checklist" ] && { echo -e "$output"; return; }

    # Layer 3: Detailed Context
    output+="---\n\n"
    output+="## Detailed Context\n\n"

    for node in "${!NODE_FILES[@]}"; do
        local files="${NODE_FILES[$node]}"
        local file_count=$(echo "$files" | grep -v '^$' | wc -l | tr -d ' ')

        output+="### ${node}\n\n"
        output+="**Covers:** ${file_count} changed files\n\n"

        # Show relevant sections from node
        local content="${NODE_CONTENT[$node]}"

        # Extract Contracts section
        local contracts=$(echo "$content" | sed -n '/## Contracts/,/^## /p' | head -20 || echo "")
        if [ -n "$contracts" ]; then
            output+="#### Contracts\n\n"
            output+="${contracts}\n\n"
        fi

        # Extract Pitfalls section
        local pitfalls=$(echo "$content" | sed -n '/## Pitfalls/,/^## /p' | head -20 || echo "")
        if [ -n "$pitfalls" ]; then
            output+="#### Pitfalls\n\n"
            output+="${pitfalls}\n\n"
        fi

        output+="---\n\n"
    done

    echo -e "$output"
}

# Output
if [ -n "$OUTPUT_FILE" ]; then
    generate_output > "$OUTPUT_FILE"
    echo "Output written to: $OUTPUT_FILE"
else
    generate_output
fi

# Exit code mode
if [ "$EXIT_CODE_MODE" = true ]; then
    case $RISK_LEVEL in
        "Low") exit 0 ;;
        "Medium") exit 1 ;;
        "High") exit 2 ;;
    esac
fi
