#!/usr/bin/env bash
# Comprehensive audit of Intent Layer health: validation, staleness, coverage
# Usage: ./audit_intent_layer.sh [OPTIONS] [PATH]

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
audit_intent_layer.sh - Comprehensive Intent Layer audit

USAGE:
    audit_intent_layer.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to audit (default: current directory)

OPTIONS:
    -h, --help      Show this help message
    --json          Output in JSON format for CI integration
    --quick         Fast check: root + immediate children only (skip consistency)

AUDIT COMPONENTS:
    1. VALIDATION   - Run validate_node.sh on all nodes (PASS/WARN/FAIL counts)
    2. STALENESS    - Categorize by age (Fresh/Aging/Stale)
    3. COVERAGE     - Find code directories without covering AGENTS.md
    4. CONSISTENCY  - Check sibling nodes use same sections (skipped with --quick)

EXIT CODES:
    0    HEALTHY - no issues
    1    NEEDS_ATTENTION - warnings only
    2    CRITICAL - failures or >50% stale nodes

EXAMPLES:
    audit_intent_layer.sh                      # Full audit of current directory
    audit_intent_layer.sh --quick              # Fast check (root + children)
    audit_intent_layer.sh --json .             # JSON output for CI
    audit_intent_layer.sh /path/to/project     # Audit specific project
EOF
    exit 0
}

# Script directory for calling sibling scripts
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common.sh for setup_colors
if [[ -f "$SCRIPT_DIR/../lib/common.sh" ]]; then
    # shellcheck source=../lib/common.sh
    source "$SCRIPT_DIR/../lib/common.sh"
    setup_colors
else
    RED=''; GREEN=''; YELLOW=''; BOLD=''; DIM=''; RESET=''
fi

# Defaults
TARGET_PATH="."
JSON_OUTPUT=false
QUICK_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            TARGET_PATH="$1"
            shift
            ;;
    esac
done

# Validate path
if [ ! -d "$TARGET_PATH" ]; then
    echo "Error: Directory not found: $TARGET_PATH" >&2
    exit 1
fi

TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

# Check if git repo
IS_GIT_REPO=false
if git -C "$TARGET_PATH" rev-parse --git-dir > /dev/null 2>&1; then
    IS_GIT_REPO=true
fi

# Common exclusions for find commands
EXCLUSIONS=(
    -not -path "*/node_modules/*"
    -not -path "*/.git/*"
    -not -path "*/dist/*"
    -not -path "*/build/*"
    -not -path "*/public/*"
    -not -path "*/target/*"
    -not -path "*/.turbo/*"
    -not -path "*/vendor/*"
    -not -path "*/.venv/*"
    -not -path "*/venv/*"
    -not -path "*/.worktrees/*"
    -not -path "*/__pycache__/*"
)

# ============================================================
# Utility Functions
# ============================================================

# Get file modification time (cross-platform)
get_mtime() {
    local file="$1"
    if stat -f %m "$file" 2>/dev/null; then
        return
    elif stat -c %Y "$file" 2>/dev/null; then
        return
    fi
    echo "0"
}

# Calculate days since modification
days_since_modified() {
    local file="$1"
    local mtime
    mtime=$(get_mtime "$file")
    local now
    now=$(date +%s)
    echo $(( (now - mtime) / 86400 ))
}

# Format tokens for display
format_tokens() {
    local tokens=$1
    if [ "$tokens" -ge 1000 ]; then
        echo "$(echo "scale=1; $tokens/1000" | bc 2>/dev/null || echo "$tokens")k"
    else
        echo "$tokens"
    fi
}

# Find all Intent Layer nodes
find_nodes() {
    local path="$1"
    local max_depth="${2:-}"

    local depth_arg=""
    if [ -n "$max_depth" ]; then
        depth_arg="-maxdepth $max_depth"
    fi

    # shellcheck disable=SC2086
    find "$path" $depth_arg \( -name "AGENTS.md" -o -name "CLAUDE.md" \) -type f "${EXCLUSIONS[@]}" 2>/dev/null | sort || true
}

# Find covering node for a path (simplified inline version)
find_covering_node() {
    local file_path="$1"
    local current_dir

    if [ -d "$file_path" ]; then
        current_dir="$file_path"
    else
        current_dir=$(dirname "$file_path")
    fi

    while [ "$current_dir" != "/" ]; do
        if [ -f "$current_dir/AGENTS.md" ]; then
            echo "$current_dir/AGENTS.md"
            return
        fi
        if [ -f "$current_dir/CLAUDE.md" ]; then
            echo "$current_dir/CLAUDE.md"
            return
        fi
        # Stop at git root
        if [ -d "$current_dir/.git" ]; then
            break
        fi
        current_dir=$(dirname "$current_dir")
    done
}

# ============================================================
# 1. VALIDATION AUDIT
# ============================================================

run_validation_audit() {
    local nodes=("$@")
    local pass=0
    local warn=0
    local fail=0
    local issues=()

    for node in "${nodes[@]}"; do
        [ -z "$node" ] && continue
        [ ! -f "$node" ] && continue

        # Run validate_node.sh in quiet mode and check exit code
        local result=""
        local exit_code=0

        if [ -x "$SCRIPT_DIR/validate_node.sh" ]; then
            result=$("$SCRIPT_DIR/validate_node.sh" -q "$node" 2>&1) || exit_code=$?
        else
            # Inline basic validation if script not available
            local bytes tokens
            bytes=$(wc -c < "$node" | tr -d ' ')
            tokens=$((bytes / 4))

            if [ "$tokens" -gt 4000 ]; then
                exit_code=1
            fi
        fi

        local rel_path="${node#$TARGET_PATH/}"

        case $exit_code in
            0)
                # Check if there were warnings by examining output or running full validation
                local full_output
                full_output=$("$SCRIPT_DIR/validate_node.sh" "$node" 2>&1) || true
                if echo "$full_output" | grep -q "Warnings:.*[1-9]"; then
                    warn=$((warn + 1))
                    # Extract warning count
                    local warn_count
                    warn_count=$(echo "$full_output" | grep "Warnings:" | grep -oE '[0-9]+' | head -1)
                    issues+=("WARN|$rel_path|$warn_count warning(s)")
                else
                    pass=$((pass + 1))
                fi
                ;;
            1)
                fail=$((fail + 1))
                issues+=("FAIL|$rel_path|validation errors")
                ;;
            *)
                fail=$((fail + 1))
                issues+=("FAIL|$rel_path|unknown error")
                ;;
        esac
    done

    # Output format: pass|warn|fail|issues (newline-separated after third |)
    local issues_str=""
    if [ ${#issues[@]} -gt 0 ]; then
        # Use semicolon to separate issues (avoid newline in pipe output)
        issues_str=$(IFS=';'; echo "${issues[*]}")
    fi

    echo "$pass|$warn|$fail|$issues_str"
}

# ============================================================
# 2. STALENESS AUDIT
# ============================================================

run_staleness_audit() {
    local nodes=("$@")
    local fresh=0      # <30 days
    local aging=0      # 30-90 days
    local stale=0      # >90 days
    local stale_nodes=()

    for node in "${nodes[@]}"; do
        [ -z "$node" ] && continue
        [ ! -f "$node" ] && continue

        local days
        days=$(days_since_modified "$node")
        local rel_path="${node#$TARGET_PATH/}"

        if [ "$days" -lt 30 ]; then
            fresh=$((fresh + 1))
        elif [ "$days" -lt 90 ]; then
            aging=$((aging + 1))
        else
            stale=$((stale + 1))
            stale_nodes+=("$rel_path|$days")
        fi
    done

    local stale_str=""
    if [ ${#stale_nodes[@]} -gt 0 ]; then
        # Use semicolon to separate entries (avoid newline in pipe output)
        stale_str=$(IFS=';'; echo "${stale_nodes[*]}")
    fi

    echo "$fresh|$aging|$stale|$stale_str"
}

# ============================================================
# 3. COVERAGE AUDIT
# ============================================================

run_coverage_audit() {
    local code_extensions=("ts" "tsx" "js" "jsx" "py" "go" "rs" "java" "rb" "php" "c" "cpp" "h" "hpp" "cs" "swift" "kt")

    # Find all directories containing code files
    local code_dirs=()
    local covered=0
    local uncovered=0
    local uncovered_dirs=()

    # Build find command for code files
    local ext_pattern=""
    for ext in "${code_extensions[@]}"; do
        if [ -z "$ext_pattern" ]; then
            ext_pattern="-name \"*.$ext\""
        else
            ext_pattern="$ext_pattern -o -name \"*.$ext\""
        fi
    done

    # Find directories with code files
    while IFS= read -r dir; do
        [ -z "$dir" ] && continue

        # Check if this directory has a covering node
        local covering_node
        covering_node=$(find_covering_node "$dir")

        if [ -n "$covering_node" ]; then
            covered=$((covered + 1))
        else
            uncovered=$((uncovered + 1))

            # Estimate tokens for uncovered directory
            local bytes=0
            while IFS= read -r file; do
                [ -z "$file" ] && continue
                local file_bytes
                file_bytes=$(wc -c < "$file" 2>/dev/null | tr -d ' ') || file_bytes=0
                bytes=$((bytes + file_bytes))
            done < <(find "$dir" -maxdepth 1 -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.py" -o -name "*.go" -o -name "*.rs" -o -name "*.java" \) 2>/dev/null || true)

            local tokens=$((bytes / 4))
            local rel_dir="${dir#$TARGET_PATH/}"
            uncovered_dirs+=("$tokens|$rel_dir")
        fi
    done < <(find "$TARGET_PATH" -type d "${EXCLUSIONS[@]}" 2>/dev/null | while read -r d; do
        # Check if directory has code files directly (not subdirs)
        if find "$d" -maxdepth 1 -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.py" -o -name "*.go" -o -name "*.rs" -o -name "*.java" -o -name "*.rb" -o -name "*.php" -o -name "*.c" -o -name "*.cpp" -o -name "*.cs" -o -name "*.swift" -o -name "*.kt" \) 2>/dev/null | head -1 | grep -q .; then
            echo "$d"
        fi
    done | sort -u || true)

    # Sort uncovered by size (descending) and take top 5
    local top_uncovered=""
    if [ ${#uncovered_dirs[@]} -gt 0 ]; then
        # Sort by token count (first field), take top 5, join with semicolons
        top_uncovered=$(printf '%s\n' "${uncovered_dirs[@]}" | sort -t'|' -k1 -rn | head -5 | tr '\n' ';' | sed 's/;$//')
    fi

    local total=$((covered + uncovered))
    local pct=0
    if [ "$total" -gt 0 ]; then
        pct=$((covered * 100 / total))
    fi

    echo "$pct|$covered|$total|$top_uncovered"
}

# ============================================================
# 4. CONSISTENCY AUDIT (skip in quick mode)
# ============================================================

run_consistency_audit() {
    local nodes=("$@")

    # Extract sections from each node and compare siblings
    local sections_map=""
    local total_siblings=0
    local aligned_siblings=0

    # Group nodes by parent directory
    declare -A parent_groups
    for node in "${nodes[@]}"; do
        [ -z "$node" ] && continue
        local parent
        parent=$(dirname "$(dirname "$node")")
        parent_groups["$parent"]+="$node "
    done

    # For each group of siblings, check section alignment
    for parent in "${!parent_groups[@]}"; do
        local siblings=(${parent_groups[$parent]})
        [ ${#siblings[@]} -lt 2 ] && continue

        total_siblings=$((total_siblings + ${#siblings[@]}))

        # Get sections from first sibling as reference
        local ref_sections=""
        if [ -f "${siblings[0]}" ]; then
            ref_sections=$(grep -E '^##+ ' "${siblings[0]}" 2>/dev/null | sort | uniq || true)
        fi

        # Compare each sibling's sections
        for sibling in "${siblings[@]}"; do
            [ ! -f "$sibling" ] && continue
            local sibling_sections
            sibling_sections=$(grep -E '^##+ ' "$sibling" 2>/dev/null | sort | uniq || true)

            if [ "$sibling_sections" = "$ref_sections" ]; then
                aligned_siblings=$((aligned_siblings + 1))
            fi
        done
    done

    local pct=100
    if [ "$total_siblings" -gt 0 ]; then
        pct=$((aligned_siblings * 100 / total_siblings))
    fi

    echo "$pct|$aligned_siblings|$total_siblings"
}

# ============================================================
# Main Audit Logic
# ============================================================

# Find all nodes (or limited set in quick mode)
ALL_NODES=()
if [ "$QUICK_MODE" = true ]; then
    while IFS= read -r node; do
        [ -n "$node" ] && ALL_NODES+=("$node")
    done < <(find_nodes "$TARGET_PATH" 2)
else
    while IFS= read -r node; do
        [ -n "$node" ] && ALL_NODES+=("$node")
    done < <(find_nodes "$TARGET_PATH")
fi

NODE_COUNT=${#ALL_NODES[@]}

# Run audits
VALIDATION_RESULT=$(run_validation_audit "${ALL_NODES[@]}")
STALENESS_RESULT=$(run_staleness_audit "${ALL_NODES[@]}")
COVERAGE_RESULT=$(run_coverage_audit)

CONSISTENCY_RESULT="100|0|0"
if [ "$QUICK_MODE" = false ] && [ "$NODE_COUNT" -gt 1 ]; then
    CONSISTENCY_RESULT=$(run_consistency_audit "${ALL_NODES[@]}")
fi

# Parse results
IFS='|' read -r VAL_PASS VAL_WARN VAL_FAIL VAL_ISSUES <<< "$VALIDATION_RESULT"
IFS='|' read -r STALE_FRESH STALE_AGING STALE_STALE STALE_NODES <<< "$STALENESS_RESULT"
IFS='|' read -r COV_PCT COV_COVERED COV_TOTAL COV_GAPS <<< "$COVERAGE_RESULT"
IFS='|' read -r CONS_PCT CONS_ALIGNED CONS_TOTAL <<< "$CONSISTENCY_RESULT"

# Determine overall status
OVERALL_STATUS="HEALTHY"
EXIT_CODE=0
ISSUE_COUNT=0

# Critical conditions
if [ "$VAL_FAIL" -gt 0 ]; then
    OVERALL_STATUS="CRITICAL"
    EXIT_CODE=2
    ISSUE_COUNT=$((ISSUE_COUNT + VAL_FAIL))
fi

# Calculate stale percentage
STALE_PCT=0
if [ "$NODE_COUNT" -gt 0 ]; then
    STALE_PCT=$((STALE_STALE * 100 / NODE_COUNT))
fi

if [ "$STALE_PCT" -gt 50 ]; then
    OVERALL_STATUS="CRITICAL"
    EXIT_CODE=2
fi

# Warning conditions (only if not already critical)
if [ "$EXIT_CODE" -lt 2 ]; then
    # Only count low coverage as issue if there are directories to cover
    LOW_COVERAGE=false
    if [ "$COV_TOTAL" -gt 0 ] && [ "$COV_PCT" -lt 80 ]; then
        LOW_COVERAGE=true
    fi

    if [ "$VAL_WARN" -gt 0 ] || [ "$STALE_STALE" -gt 0 ] || [ "$LOW_COVERAGE" = true ]; then
        OVERALL_STATUS="NEEDS_ATTENTION"
        EXIT_CODE=1
        ISSUE_COUNT=$((ISSUE_COUNT + VAL_WARN + STALE_STALE))
        if [ "$LOW_COVERAGE" = true ]; then
            ISSUE_COUNT=$((ISSUE_COUNT + 1))
        fi
    fi
fi

# ============================================================
# Output
# ============================================================

if [ "$JSON_OUTPUT" = true ]; then
    # Build JSON output

    # Validation issues array (semicolon-separated entries, pipe-separated fields)
    val_issues_json="[]"
    if [ -n "$VAL_ISSUES" ]; then
        val_issues_json="["
        first=true
        IFS=';' read -ra issue_arr <<< "$VAL_ISSUES"
        for entry in "${issue_arr[@]}"; do
            [ -z "$entry" ] && continue
            IFS='|' read -r level path desc <<< "$entry"
            [ -z "$level" ] && continue
            if [ "$first" = true ]; then
                first=false
            else
                val_issues_json+=","
            fi
            val_issues_json+="{\"level\":\"$level\",\"path\":\"$path\",\"description\":\"$desc\"}"
        done
        val_issues_json+="]"
    fi

    # Stale nodes array (semicolon-separated entries, pipe-separated fields)
    stale_nodes_json="[]"
    if [ -n "$STALE_NODES" ]; then
        stale_nodes_json="["
        first=true
        IFS=';' read -ra stale_arr <<< "$STALE_NODES"
        for entry in "${stale_arr[@]}"; do
            [ -z "$entry" ] && continue
            IFS='|' read -r path days <<< "$entry"
            [ -z "$path" ] && continue
            if [ "$first" = true ]; then
                first=false
            else
                stale_nodes_json+=","
            fi
            stale_nodes_json+="{\"path\":\"$path\",\"days\":$days}"
        done
        stale_nodes_json+="]"
    fi

    # Coverage gaps array (semicolon-separated entries, pipe-separated fields)
    coverage_gaps_json="[]"
    if [ -n "$COV_GAPS" ]; then
        coverage_gaps_json="["
        first=true
        IFS=';' read -ra gap_arr <<< "$COV_GAPS"
        for entry in "${gap_arr[@]}"; do
            [ -z "$entry" ] && continue
            IFS='|' read -r tokens path <<< "$entry"
            [ -z "$tokens" ] && continue
            if [ "$first" = true ]; then
                first=false
            else
                coverage_gaps_json+=","
            fi
            local tokens_fmt
            tokens_fmt=$(format_tokens "$tokens")
            coverage_gaps_json+="{\"path\":\"$path\",\"tokens\":\"$tokens_fmt\"}"
        done
        coverage_gaps_json+="]"
    fi

    cat << EOF
{
  "status": "$OVERALL_STATUS",
  "exitCode": $EXIT_CODE,
  "issueCount": $ISSUE_COUNT,
  "quickMode": $QUICK_MODE,
  "validation": {
    "nodesChecked": $NODE_COUNT,
    "pass": $VAL_PASS,
    "warn": $VAL_WARN,
    "fail": $VAL_FAIL,
    "issues": $val_issues_json
  },
  "staleness": {
    "fresh": $STALE_FRESH,
    "aging": $STALE_AGING,
    "stale": $STALE_STALE,
    "staleNodes": $stale_nodes_json
  },
  "coverage": {
    "percentage": $COV_PCT,
    "covered": $COV_COVERED,
    "total": $COV_TOTAL,
    "gaps": $coverage_gaps_json
  },
  "consistency": {
    "percentage": $CONS_PCT,
    "aligned": $CONS_ALIGNED,
    "total": $CONS_TOTAL
  }
}
EOF
    exit $EXIT_CODE
fi

# Text output
echo "${BOLD}Intent Layer Audit Report${RESET}"
echo "${BOLD}=========================${RESET}"
echo ""

echo "${BOLD}VALIDATION${RESET} ($NODE_COUNT nodes checked)"
echo "  ${GREEN}✓${RESET} PASS: $VAL_PASS nodes"
if [ "$VAL_WARN" -gt 0 ]; then
    echo "  ${YELLOW}⚠${RESET} WARN: ${YELLOW}$VAL_WARN${RESET} nodes"
else
    echo "  ${GREEN}⚠${RESET} WARN: $VAL_WARN nodes"
fi
if [ "$VAL_FAIL" -gt 0 ]; then
    echo "  ${RED}✗${RESET} FAIL: ${RED}$VAL_FAIL${RESET} nodes"
else
    echo "  ${GREEN}✗${RESET} FAIL: $VAL_FAIL nodes"
fi

if [ -n "$VAL_ISSUES" ]; then
    IFS=';' read -ra issue_arr <<< "$VAL_ISSUES"
    for entry in "${issue_arr[@]}"; do
        [ -z "$entry" ] && continue
        IFS='|' read -r level path desc <<< "$entry"
        [ -z "$level" ] && continue
        case $level in
            FAIL) echo "    ${RED}✗${RESET} $path - $desc" ;;
            WARN) echo "    ${YELLOW}⚠${RESET} $path - $desc" ;;
        esac
    done
fi
echo ""

echo "${BOLD}STALENESS${RESET}"
echo "  ${GREEN}Fresh${RESET} (<30 days): $STALE_FRESH nodes"
if [ "$STALE_AGING" -gt 0 ]; then
    echo "  ${YELLOW}Aging${RESET} (30-90 days): ${YELLOW}$STALE_AGING${RESET} nodes"
else
    echo "  Aging (30-90 days): $STALE_AGING nodes"
fi
if [ "$STALE_STALE" -gt 0 ]; then
    echo "  ${RED}Stale${RESET} (>90 days): ${RED}$STALE_STALE${RESET} node(s)"
else
    echo "  Stale (>90 days): $STALE_STALE node(s)"
fi

if [ -n "$STALE_NODES" ]; then
    IFS=';' read -ra stale_arr <<< "$STALE_NODES"
    for entry in "${stale_arr[@]}"; do
        [ -z "$entry" ] && continue
        IFS='|' read -r path days <<< "$entry"
        [ -z "$path" ] && continue
        echo "    ${DIM}-${RESET} $path ${DIM}($days days)${RESET}"
    done
fi
echo ""

echo "${BOLD}COVERAGE${RESET}"
# Color the coverage percentage
if [ "$COV_PCT" -ge 80 ]; then
    COV_COLOR="$GREEN"
elif [ "$COV_PCT" -ge 50 ]; then
    COV_COLOR="$YELLOW"
else
    COV_COLOR="$RED"
fi
echo "  Documented: ${COV_COLOR}${COV_PCT}%${RESET} ($COV_COVERED/$COV_TOTAL directories)"

if [ -n "$COV_GAPS" ]; then
    echo "  Gaps:"
    IFS=';' read -ra gap_arr <<< "$COV_GAPS"
    for entry in "${gap_arr[@]}"; do
        [ -z "$entry" ] && continue
        IFS='|' read -r tokens path <<< "$entry"
        [ -z "$tokens" ] && continue
        tokens_fmt=$(format_tokens "$tokens")
        echo "    ${YELLOW}-${RESET} $path ${DIM}(${tokens_fmt} tokens)${RESET}"
    done
fi
echo ""

if [ "$QUICK_MODE" = false ] && [ "$CONS_TOTAL" -gt 0 ]; then
    echo "${BOLD}CONSISTENCY${RESET}"
    if [ "$CONS_PCT" -ge 80 ]; then
        CONS_COLOR="$GREEN"
    elif [ "$CONS_PCT" -ge 50 ]; then
        CONS_COLOR="$YELLOW"
    else
        CONS_COLOR="$RED"
    fi
    echo "  Section alignment: ${CONS_COLOR}${CONS_PCT}%${RESET} ($CONS_ALIGNED/$CONS_TOTAL sibling nodes)"
    echo ""
fi

# Color the overall status
case "$OVERALL_STATUS" in
    HEALTHY) STATUS_COLOR="$GREEN" ;;
    NEEDS_ATTENTION) STATUS_COLOR="$YELLOW" ;;
    CRITICAL) STATUS_COLOR="$RED" ;;
    *) STATUS_COLOR="" ;;
esac
echo "${BOLD}OVERALL:${RESET} ${STATUS_COLOR}${OVERALL_STATUS}${RESET} ($ISSUE_COUNT issue(s))"

exit $EXIT_CODE
