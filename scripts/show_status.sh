#!/usr/bin/env bash
# Show Intent Layer status dashboard with health metrics
# Usage: ./show_status.sh [options] [path]

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
show_status.sh - Intent Layer status dashboard

USAGE:
    show_status.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    -h, --help    Show this help message
    -j, --json    Output in JSON format for programmatic use

OUTPUT:
    Dashboard showing:
    - State indicator (none/partial/complete) with emoji
    - Summary statistics (node count, total tokens, errors, warnings)
    - Per-node health table with token budget percentage
    - Actionable recommendations

EXAMPLES:
    show_status.sh                    # Check current directory
    show_status.sh /path/to/project   # Check specific project
    show_status.sh --json .           # JSON output for scripting
EOF
    exit 0
}

# Parse arguments
JSON_OUTPUT=false
TARGET_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -j|--json)
            JSON_OUTPUT=true
            shift
            ;;
        -*)
            echo "❌ Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [ -n "$TARGET_PATH" ]; then
                echo "❌ Error: Multiple paths specified" >&2
                exit 1
            fi
            TARGET_PATH="$1"
            shift
            ;;
    esac
done

TARGET_PATH="${TARGET_PATH:-.}"

# Source common.sh for setup_colors
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/../lib/common.sh" ]]; then
    # shellcheck source=../lib/common.sh
    source "$SCRIPT_DIR/../lib/common.sh"
    setup_colors
else
    RED=''; GREEN=''; YELLOW=''; BOLD=''; DIM=''; RESET=''
fi

# Validate path exists
if [ ! -d "$TARGET_PATH" ]; then
    echo "❌ Error: Directory not found: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Please check:" >&2
    echo "     • The path is spelled correctly" >&2
    echo "     • The directory exists" >&2
    exit 1
fi

# Validate path is readable
if [ ! -r "$TARGET_PATH" ]; then
    echo "❌ Error: Permission denied reading: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Try: chmod +r \"$TARGET_PATH\"" >&2
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

# Common exclusions
EXCLUSIONS="-not -path \"*/node_modules/*\" -not -path \"*/.git/*\" -not -path \"*/dist/*\" -not -path \"*/build/*\" -not -path \"*/public/*\" -not -path \"*/target/*\" -not -path \"*/.turbo/*\" -not -path \"*/vendor/*\" -not -path \"*/.venv/*\" -not -path \"*/venv/*\" -not -path \"*/.worktrees/*\""

# Find root file
ROOT_FILE=""
if [ -f "$TARGET_PATH/CLAUDE.md" ]; then
    ROOT_FILE="CLAUDE.md"
elif [ -f "$TARGET_PATH/AGENTS.md" ]; then
    ROOT_FILE="AGENTS.md"
fi

# Check for Intent Layer section
HAS_INTENT_SECTION=false
if [ -n "$ROOT_FILE" ] && [ -r "$TARGET_PATH/$ROOT_FILE" ]; then
    if grep -q "## Intent Layer" "$TARGET_PATH/$ROOT_FILE" 2>/dev/null; then
        HAS_INTENT_SECTION=true
    fi
fi

# Determine state
STATE="none"
STATE_EMOJI="🔴"
STATE_COLOR="$RED"
if [ -z "$ROOT_FILE" ]; then
    STATE="none"
    STATE_EMOJI="🔴"
    STATE_COLOR="$RED"
elif [ "$HAS_INTENT_SECTION" = false ]; then
    STATE="partial"
    STATE_EMOJI="🟡"
    STATE_COLOR="$YELLOW"
else
    STATE="complete"
    STATE_EMOJI="🟢"
    STATE_COLOR="$GREEN"
fi

# Find all nodes
NODES=()
if [ -n "$ROOT_FILE" ]; then
    NODES+=("$TARGET_PATH/$ROOT_FILE")
fi

while IFS= read -r file; do
    if [ -n "$file" ] && [ "$file" != "$TARGET_PATH/AGENTS.md" ]; then
        NODES+=("$file")
    fi
done < <(eval "find \"$TARGET_PATH\" -name \"AGENTS.md\" -not -path \"$TARGET_PATH/AGENTS.md\" $EXCLUSIONS 2>/dev/null" || true)

# Calculate metrics for each node
NODE_DATA=()
TOTAL_TOKENS=0
TOTAL_ERRORS=0
TOTAL_WARNINGS=0
STALE_NODES=0

get_file_age_days() {
    local file="$1"
    local mtime=""
    if mtime=$(stat -f %m "$file" 2>/dev/null); then
        : # macOS
    elif mtime=$(stat -c %Y "$file" 2>/dev/null); then
        : # Linux
    else
        echo "?"
        return
    fi
    local now=$(date +%s)
    echo $(( (now - mtime) / 86400 ))
}

format_tokens() {
    local tokens=$1
    if [ "$tokens" -ge 1000 ]; then
        echo "~$(echo "scale=1; $tokens/1000" | bc 2>/dev/null || echo "$tokens")k"
    else
        echo "~$tokens"
    fi
}

TOKEN_BUDGET=4000

for node in ${NODES[@]+"${NODES[@]}"}; do
    if [ ! -r "$node" ]; then
        continue
    fi

    bytes=$(wc -c < "$node" 2>/dev/null | tr -d ' ') || bytes=0
    tokens=$((bytes / 4))
    TOTAL_TOKENS=$((TOTAL_TOKENS + tokens))

    budget_pct=$((tokens * 100 / TOKEN_BUDGET))

    age=$(get_file_age_days "$node")

    # Determine status
    status="✓"
    node_errors=0
    node_warnings=0

    # Check token count
    if [ "$tokens" -gt 4000 ]; then
        status="✗"
        node_errors=1
    elif [ "$tokens" -gt 3000 ]; then
        status="⚠"
        node_warnings=1
    fi

    # Check staleness
    if [[ "$age" =~ ^[0-9]+$ ]] && [ "$age" -gt 90 ]; then
        if [ "$status" = "✓" ]; then
            status="⚠"
        fi
        node_warnings=$((node_warnings + 1))
        STALE_NODES=$((STALE_NODES + 1))
    fi

    TOTAL_ERRORS=$((TOTAL_ERRORS + node_errors))
    TOTAL_WARNINGS=$((TOTAL_WARNINGS + node_warnings))

    # Store node data
    rel_path="${node#$TARGET_PATH/}"
    NODE_DATA+=("$rel_path|$tokens|$budget_pct|$status|$age")
done

# Format total tokens
TOTAL_TOKENS_FMT=$(format_tokens $TOTAL_TOKENS)

# Generate recommendations
RECOMMENDATIONS=()

if [ "$STATE" = "none" ]; then
    RECOMMENDATIONS+=("Create root CLAUDE.md or AGENTS.md file")
elif [ "$STATE" = "partial" ]; then
    RECOMMENDATIONS+=("Add Intent Layer section to $ROOT_FILE")
fi

if [ $TOTAL_ERRORS -gt 0 ]; then
    RECOMMENDATIONS+=("Fix $TOTAL_ERRORS node(s) exceeding 4k token budget")
fi

if [ $STALE_NODES -gt 0 ]; then
    RECOMMENDATIONS+=("Review $STALE_NODES stale node(s) for accuracy")
fi

if [ ${#NODES[@]} -eq 1 ] && [ "$STATE" = "complete" ]; then
    RECOMMENDATIONS+=("Consider adding child AGENTS.md for large subdirectories")
fi

if [ ${#RECOMMENDATIONS[@]} -eq 0 ] && [ "$STATE" = "complete" ]; then
    RECOMMENDATIONS+=("Intent Layer is healthy - run maintenance quarterly")
fi

# Output JSON if requested
if [ "$JSON_OUTPUT" = true ]; then
    # Build nodes JSON array
    nodes_json="["
    first=true
    for data in ${NODE_DATA[@]+"${NODE_DATA[@]}"}; do
        IFS='|' read -r path tokens budget status age <<< "$data"
        if [ "$first" = true ]; then
            first=false
        else
            nodes_json+=","
        fi
        nodes_json+="{\"path\":\"$path\",\"tokens\":$tokens,\"budgetPct\":$budget,\"status\":\"$status\",\"ageDays\":\"$age\"}"
    done
    nodes_json+="]"

    # Build recommendations JSON array
    recs_json="["
    first=true
    for rec in ${RECOMMENDATIONS[@]+"${RECOMMENDATIONS[@]}"}; do
        if [ "$first" = true ]; then
            first=false
        else
            recs_json+=","
        fi
        recs_json+="\"$rec\""
    done
    recs_json+="]"

    cat << EOF
{
  "state": "$STATE",
  "rootFile": "${ROOT_FILE:-null}",
  "totalNodes": ${#NODES[@]},
  "totalTokens": $TOTAL_TOKENS,
  "errors": $TOTAL_ERRORS,
  "warnings": $TOTAL_WARNINGS,
  "staleNodes": $STALE_NODES,
  "nodes": $nodes_json,
  "recommendations": $recs_json
}
EOF
    exit 0
fi

# Output dashboard
echo "${BOLD}╔════════════════════════════════════════╗${RESET}"
echo "${BOLD}║     INTENT LAYER STATUS DASHBOARD      ║${RESET}"
echo "${BOLD}╚════════════════════════════════════════╝${RESET}"
echo ""

echo "${BOLD}State:${RESET} $STATE_EMOJI ${STATE_COLOR}$(echo "$STATE" | tr '[:lower:]' '[:upper:]')${RESET}"
echo ""

echo "${BOLD}Summary${RESET}"
echo "  Root File:    ${ROOT_FILE:-none}"
echo "  Total Nodes:  ${#NODES[@]}"
echo "  Total Tokens: $TOTAL_TOKENS_FMT"
if [ "$TOTAL_ERRORS" -gt 0 ]; then
    echo "  Errors:       ${RED}${TOTAL_ERRORS}${RESET}"
else
    echo "  Errors:       ${GREEN}${TOTAL_ERRORS}${RESET}"
fi
if [ "$TOTAL_WARNINGS" -gt 0 ]; then
    echo "  Warnings:     ${YELLOW}${TOTAL_WARNINGS}${RESET}"
else
    echo "  Warnings:     ${TOTAL_WARNINGS}"
fi
echo ""

if [ ${#NODES[@]} -gt 0 ]; then
    echo "${BOLD}Node Health${RESET}"
    printf "  ${DIM}%-40s %-8s %-8s %-8s %s${RESET}\n" "Node" "Tokens" "Budget" "Status" "Age"
    for data in ${NODE_DATA[@]+"${NODE_DATA[@]}"}; do
        IFS='|' read -r path tokens budget status age <<< "$data"
        tokens_fmt=$(format_tokens $tokens)
        # Color the status indicator
        case "$status" in
            "✓") colored_status="${GREEN}✓${RESET}" ;;
            "⚠") colored_status="${YELLOW}⚠${RESET}" ;;
            "✗") colored_status="${RED}✗${RESET}" ;;
            *) colored_status="$status" ;;
        esac
        # Color the budget percentage
        if [ "$budget" -gt 100 ]; then
            colored_budget="${RED}${budget}%${RESET}"
        elif [ "$budget" -gt 75 ]; then
            colored_budget="${YELLOW}${budget}%${RESET}"
        else
            colored_budget="${GREEN}${budget}%${RESET}"
        fi
        printf "  %-40s %-8s %-8b %-8b %s\n" "$path" "$tokens_fmt" "$colored_budget" "$colored_status" "${DIM}${age}d${RESET}"
    done
    echo ""
fi

echo "${BOLD}Recommended Actions${RESET}"
for rec in ${RECOMMENDATIONS[@]+"${RECOMMENDATIONS[@]}"}; do
    echo "  - $rec"
done
echo ""
