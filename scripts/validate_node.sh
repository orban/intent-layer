#!/usr/bin/env bash
# Validate an Intent Node (CLAUDE.md or AGENTS.md) against quality standards
# Usage: ./validate_node.sh <path_to_node>
#
# Checks:
# - Token count < 4k (warning at 3k)
# - Required sections present
# - No absolute paths in links
# - No common anti-patterns
# - Structure follows template

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
validate_node.sh - Validate Intent Node quality

USAGE:
    validate_node.sh [OPTIONS] <FILE>

ARGUMENTS:
    FILE    Path to CLAUDE.md or AGENTS.md file to validate

OPTIONS:
    -h, --help    Show this help message
    -q, --quiet   Only output errors (exit code indicates pass/fail)

CHECKS:
    ✓ Token count < 4k (warning at 3k)
    ✓ Required sections present (Intent Layer for root, Purpose for child)
    ✓ No absolute paths in internal links
    ✓ No TODO/FIXME markers
    ✓ Contains code examples
    ✓ No verbose boilerplate language
    ✓ Reasonable line lengths

EXIT CODES:
    0    Validation passed (may have warnings)
    1    Validation failed (has errors)

EXAMPLES:
    validate_node.sh ./CLAUDE.md
    validate_node.sh src/api/AGENTS.md
    validate_node.sh --quiet ./CLAUDE.md && echo "Valid!"
EOF
    exit 0
}

# Parse arguments
QUIET=false
NODE_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -*)
            echo "❌ Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [ -n "$NODE_PATH" ]; then
                echo "❌ Error: Multiple files specified" >&2
                echo "   validate_node.sh only accepts one file at a time" >&2
                exit 1
            fi
            NODE_PATH="$1"
            shift
            ;;
    esac
done

# Validate input
if [ -z "$NODE_PATH" ]; then
    echo "❌ Error: No file specified" >&2
    echo "" >&2
    echo "   Usage: validate_node.sh <path_to_file>" >&2
    echo "   Example: validate_node.sh ./CLAUDE.md" >&2
    echo "" >&2
    echo "   Run with --help for more information" >&2
    exit 1
fi

if [ ! -f "$NODE_PATH" ]; then
    echo "❌ Error: File not found: $NODE_PATH" >&2
    echo "" >&2
    echo "   Please check:" >&2
    echo "     • The file path is correct" >&2
    echo "     • The file exists" >&2
    echo "     • You're in the right directory" >&2
    exit 1
fi

if [ ! -r "$NODE_PATH" ]; then
    echo "❌ Error: Cannot read file: $NODE_PATH" >&2
    echo "" >&2
    echo "   Try: chmod +r \"$NODE_PATH\"" >&2
    exit 1
fi

# Resolve to absolute path for consistent root detection
resolve_path() {
    local path="$1"
    if command -v realpath &>/dev/null; then
        realpath "$path"
    elif command -v readlink &>/dev/null && readlink -f "$path" &>/dev/null 2>&1; then
        readlink -f "$path"
    else
        echo "$(cd "$(dirname "$path")" && pwd)/$(basename "$path")"
    fi
}

NODE_PATH=$(resolve_path "$NODE_PATH")
NODE_DIR=$(dirname "$NODE_PATH")
FILENAME=$(basename "$NODE_PATH")

# Determine if this is the root node by checking for ancestor nodes
has_ancestor_node() {
    local dir="$1"
    local parent
    parent=$(dirname "$dir")
    while [ "$parent" != "/" ] && [ "$parent" != "." ]; do
        if [ -f "$parent/AGENTS.md" ] || [ -f "$parent/CLAUDE.md" ]; then
            return 0
        fi
        # Stop early at git root if present
        if [ -d "$parent/.git" ]; then
            break
        fi
        parent=$(dirname "$parent")
    done
    return 1
}

IS_ROOT=false
if [[ "$FILENAME" == "CLAUDE.md" || "$FILENAME" == "AGENTS.md" ]]; then
    if ! has_ancestor_node "$NODE_DIR"; then
        IS_ROOT=true
    fi
fi

if [ "$QUIET" = false ]; then
    echo "=== Intent Node Validation ==="
    echo "File: $NODE_PATH"
    echo "Type: $([ "$IS_ROOT" = true ] && echo "Root node" || echo "Child node")"
    echo ""
fi

ERRORS=()
WARNINGS=()
PASSED=()

# Check 1: Token count (using bytes/4 approximation)
BYTES=$(wc -c < "$NODE_PATH" | tr -d ' ')
if ! [[ "$BYTES" =~ ^[0-9]+$ ]]; then
    ERRORS+=("Could not determine file size")
else
    TOKENS=$((BYTES / 4))

    if [ "$TOKENS" -gt 4000 ]; then
        ERRORS+=("Token count ~$TOKENS exceeds 4k limit (compress further or split)")
    elif [ "$TOKENS" -gt 3000 ]; then
        WARNINGS+=("Token count ~$TOKENS approaching 4k limit")
    else
        PASSED+=("Token count ~$TOKENS within budget")
    fi
fi

# Check 2: Required sections for child nodes (schema)
if [ "$IS_ROOT" = false ]; then
    REQUIRED_SECTIONS=("Purpose" "Entry Points" "Contracts" "Patterns")
    for section in "${REQUIRED_SECTIONS[@]}"; do
        if grep -qiE "^##+ *$section|^##+ .*$section" "$NODE_PATH" 2>/dev/null; then
            PASSED+=("Has '$section' section")
        else
            ERRORS+=("Missing required section: '$section'")
        fi
    done
    RECOMMENDED_SECTIONS=("Code Map" "Pitfalls" "Boundaries" "Design Rationale" "Public API")
    for section in "${RECOMMENDED_SECTIONS[@]}"; do
        if grep -qiE "^##+ *$section|^##+ .*$section" "$NODE_PATH" 2>/dev/null; then
            PASSED+=("Has '$section' section")
        else
            WARNINGS+=("Missing recommended section: '$section'")
        fi
    done
else
    # Root node checks
    if grep -qi "## Intent Layer" "$NODE_PATH" 2>/dev/null; then
        PASSED+=("Has Intent Layer section")
    else
        ERRORS+=("Missing '## Intent Layer' section in root node")
    fi
    if grep -qiE "^##+ *(Entry Points|Subsystems)" "$NODE_PATH" 2>/dev/null; then
        PASSED+=("Has Entry Points or Subsystems section")
    else
        ERRORS+=("Missing required section: 'Entry Points' or 'Subsystems'")
    fi
    if grep -qiE "^##+ *Downlinks" "$NODE_PATH" 2>/dev/null; then
        PASSED+=("Has Downlinks section")
    else
        WARNINGS+=("Missing recommended section: 'Downlinks'")
    fi
fi

# Check 3: Purpose statement in first few lines
FIRST_LINES=$(head -20 "$NODE_PATH")
if echo "$FIRST_LINES" | grep -qi "purpose\|owns\|responsible\|this area\|TL;DR"; then
    PASSED+=("Purpose appears early in document")
else
    WARNINGS+=("Consider adding purpose statement or TL;DR in first few lines")
fi

# Check 4: No absolute paths (except common exceptions)
# Look for backtick-quoted paths starting with / but not common system paths
if grep -E '`/[a-zA-Z]' "$NODE_PATH" 2>/dev/null | grep -vE '`/api/|`/docs/|`/usr/|`/etc/|`/tmp/|`/bin/' | grep -q .; then
    WARNINGS+=("Contains absolute paths - prefer relative paths for portability")
else
    PASSED+=("Uses relative paths")
fi

# Check 5: No TODO/FIXME markers
if grep -qiE '\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b' "$NODE_PATH" 2>/dev/null; then
    WARNINGS+=("Contains TODO/FIXME markers - resolve before finalizing")
else
    PASSED+=("No TODO/FIXME markers")
fi

# Check 6: Has examples or code blocks
if grep -q '```' "$NODE_PATH" 2>/dev/null; then
    PASSED+=("Contains code examples")
else
    WARNINGS+=("Consider adding code examples for patterns")
fi

# Check 7: Anti-pattern detection - overly verbose language
VERBOSE_PATTERNS="This section describes|In this document|The purpose of this|It is important to note"
if grep -qiE "$VERBOSE_PATTERNS" "$NODE_PATH" 2>/dev/null; then
    WARNINGS+=("Contains verbose boilerplate - compress to essentials")
else
    PASSED+=("No verbose boilerplate detected")
fi

# Check 8: Check for passive references
if grep -qi "see also\|refer to\|please see" "$NODE_PATH" 2>/dev/null; then
    WARNINGS+=("Passive references found - use direct links instead")
fi

# Check 9: Boundaries section (recommended for child nodes)
if grep -qi "## Boundaries\|### Always\|### Never" "$NODE_PATH" 2>/dev/null; then
    PASSED+=("Has Boundaries section (three-tier pattern)")
elif [ "$IS_ROOT" = false ]; then
    WARNINGS+=("Consider adding Boundaries section (Always/Ask First/Never)")
fi

# Check 10: Line length (very long lines are hard to read)
LONG_LINES=$(awk 'length > 120' "$NODE_PATH" 2>/dev/null | wc -l | tr -d ' ')
if ! [[ "$LONG_LINES" =~ ^[0-9]+$ ]]; then
    LONG_LINES=0
fi
if [ "$LONG_LINES" -gt 5 ]; then
    WARNINGS+=("$LONG_LINES lines exceed 120 chars - consider wrapping")
else
    PASSED+=("Line lengths reasonable")
fi

# Output results
if [ "$QUIET" = false ]; then
    echo "## Results"
    echo ""

    if [ ${#ERRORS[@]} -gt 0 ]; then
        echo "### Errors (must fix)"
        for err in "${ERRORS[@]}"; do
            echo "  ✗ $err"
        done
        echo ""
    fi

    if [ ${#WARNINGS[@]} -gt 0 ]; then
        echo "### Warnings (should fix)"
        for warn in "${WARNINGS[@]}"; do
            echo "  ⚠ $warn"
        done
        echo ""
    fi

    if [ ${#PASSED[@]} -gt 0 ]; then
        echo "### Passed"
        for pass in "${PASSED[@]}"; do
            echo "  ✓ $pass"
        done
        echo ""
    fi

    # Summary
    echo "## Summary"
    echo ""
    TOTAL_CHECKS=$((${#ERRORS[@]} + ${#WARNINGS[@]} + ${#PASSED[@]}))
    echo "Passed: ${#PASSED[@]}/$TOTAL_CHECKS"
    echo "Warnings: ${#WARNINGS[@]}"
    echo "Errors: ${#ERRORS[@]}"
    echo ""
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
    if [ "$QUIET" = false ]; then
        echo "Status: FAILED - fix errors before committing"
    fi
    exit 1
elif [ ${#WARNINGS[@]} -gt 0 ]; then
    if [ "$QUIET" = false ]; then
        echo "Status: PASSED with warnings"
    fi
    exit 0
else
    if [ "$QUIET" = false ]; then
        echo "Status: PASSED"
    fi
    exit 0
fi
