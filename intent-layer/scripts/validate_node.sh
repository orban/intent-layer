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

set -e

NODE_PATH="${1:-}"

if [ -z "$NODE_PATH" ]; then
    echo "Usage: validate_node.sh <path_to_file>"
    echo "Example: validate_node.sh ./CLAUDE.md"
    exit 1
fi

if [ ! -f "$NODE_PATH" ]; then
    echo "Error: File not found: $NODE_PATH"
    exit 1
fi

if [ ! -r "$NODE_PATH" ]; then
    echo "Error: Cannot read file: $NODE_PATH"
    exit 1
fi

# Get filename for context
FILENAME=$(basename "$NODE_PATH")
IS_ROOT=false
if [ "$FILENAME" = "CLAUDE.md" ] || [ "$(dirname "$NODE_PATH")" = "." ]; then
    IS_ROOT=true
fi

echo "=== Intent Node Validation ==="
echo "File: $NODE_PATH"
echo "Type: $([ "$IS_ROOT" = true ] && echo "Root node" || echo "Child node")"
echo ""

ERRORS=()
WARNINGS=()
PASSED=()

# Check 1: Token count
BYTES=$(wc -c < "$NODE_PATH" | tr -d ' ')
TOKENS=$((BYTES / 4))

if [ "$TOKENS" -gt 4000 ]; then
    ERRORS+=("Token count ~$TOKENS exceeds 4k limit (compress further)")
elif [ "$TOKENS" -gt 3000 ]; then
    WARNINGS+=("Token count ~$TOKENS approaching 4k limit")
else
    PASSED+=("Token count ~$TOKENS within budget")
fi

# Check 2: Required sections for child nodes
if [ "$IS_ROOT" = false ]; then
    REQUIRED_SECTIONS=("Purpose" "Entry Points" "Contracts" "Patterns")
    for section in "${REQUIRED_SECTIONS[@]}"; do
        if grep -qi "## *$section" "$NODE_PATH" || grep -qi "## .*$section" "$NODE_PATH"; then
            PASSED+=("Has '$section' section")
        else
            WARNINGS+=("Missing recommended section: '$section'")
        fi
    done
else
    # Root node checks
    if grep -qi "## Intent Layer" "$NODE_PATH"; then
        PASSED+=("Has Intent Layer section")
    else
        ERRORS+=("Missing '## Intent Layer' section in root node")
    fi
fi

# Check 3: Purpose statement in first few lines
FIRST_LINES=$(head -20 "$NODE_PATH")
if echo "$FIRST_LINES" | grep -qi "purpose\|owns\|responsible\|this area"; then
    PASSED+=("Purpose appears early in document")
else
    WARNINGS+=("Consider adding purpose statement in first few lines")
fi

# Check 4: No absolute paths (except common exceptions)
if grep -E '`/[a-zA-Z]' "$NODE_PATH" | grep -vE '`/api/|`/docs/|`/usr/|`/etc/|`/tmp/' | grep -q .; then
    WARNINGS+=("Contains absolute paths - prefer relative paths for portability")
else
    PASSED+=("Uses relative paths")
fi

# Check 5: No TODO/FIXME markers
if grep -qiE '\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b' "$NODE_PATH"; then
    WARNINGS+=("Contains TODO/FIXME markers - resolve before finalizing")
else
    PASSED+=("No TODO/FIXME markers")
fi

# Check 6: Has examples or code blocks
if grep -q '```' "$NODE_PATH"; then
    PASSED+=("Contains code examples")
else
    WARNINGS+=("Consider adding code examples for patterns")
fi

# Check 7: Anti-pattern detection - overly verbose language
VERBOSE_PATTERNS="This section describes|In this document|The purpose of this|It is important to note"
if grep -qiE "$VERBOSE_PATTERNS" "$NODE_PATH"; then
    WARNINGS+=("Contains verbose boilerplate - compress to essentials")
else
    PASSED+=("No verbose boilerplate detected")
fi

# Check 8: Check for common mistakes
if grep -qi "see also\|refer to\|please see" "$NODE_PATH"; then
    WARNINGS+=("Passive references found - use direct links instead")
fi

# Check 9: Boundaries section (recommended)
if grep -qi "## Boundaries\|### Always\|### Never" "$NODE_PATH"; then
    PASSED+=("Has Boundaries section (three-tier pattern)")
elif [ "$IS_ROOT" = false ]; then
    WARNINGS+=("Consider adding Boundaries section (Always/Ask First/Never)")
fi

# Check 10: Line length (very long lines are hard to read)
LONG_LINES=$(awk 'length > 120' "$NODE_PATH" | wc -l | tr -d ' ')
if [ "$LONG_LINES" -gt 5 ]; then
    WARNINGS+=("$LONG_LINES lines exceed 120 chars - consider wrapping")
else
    PASSED+=("Line lengths reasonable")
fi

# Output results
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

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "Status: FAILED - fix errors before committing"
    exit 1
elif [ ${#WARNINGS[@]} -gt 0 ]; then
    echo "Status: PASSED with warnings"
    exit 0
else
    echo "Status: PASSED"
    exit 0
fi
