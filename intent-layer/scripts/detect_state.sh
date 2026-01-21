#!/usr/bin/env bash
# Detect Intent Layer state in a project
# Usage: ./detect_state.sh [path]
# Returns: "none" | "partial" | "complete"

set -e

TARGET_PATH="${1:-.}"

# Validate path exists and is readable
if [ ! -d "$TARGET_PATH" ]; then
    echo "Error: Path not found: $TARGET_PATH"
    exit 1
fi

if [ ! -r "$TARGET_PATH" ]; then
    echo "Error: Permission denied reading: $TARGET_PATH"
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

ROOT_FILE=""
HAS_INTENT_SECTION=false
CHILD_NODES=()
WARNINGS=()

# Find root context file (CLAUDE.md preferred over AGENTS.md)
if [ -f "$TARGET_PATH/CLAUDE.md" ]; then
    ROOT_FILE="CLAUDE.md"
    # Check if AGENTS.md also exists (conflict)
    if [ -f "$TARGET_PATH/AGENTS.md" ]; then
        WARNINGS+=("Both CLAUDE.md and AGENTS.md exist at root. Should have only one.")
    fi
elif [ -f "$TARGET_PATH/AGENTS.md" ]; then
    ROOT_FILE="AGENTS.md"
fi

# Check for Intent Layer section
if [ -n "$ROOT_FILE" ]; then
    if [ ! -r "$TARGET_PATH/$ROOT_FILE" ]; then
        WARNINGS+=("Cannot read $ROOT_FILE - permission denied")
    elif grep -q "## Intent Layer" "$TARGET_PATH/$ROOT_FILE" 2>/dev/null; then
        HAS_INTENT_SECTION=true
    fi

    # Check file age
    if [ -r "$TARGET_PATH/$ROOT_FILE" ]; then
        DAYS_OLD=$(( ($(date +%s) - $(stat -f %m "$TARGET_PATH/$ROOT_FILE" 2>/dev/null || stat -c %Y "$TARGET_PATH/$ROOT_FILE" 2>/dev/null || echo "0")) / 86400 ))
        if [ "$DAYS_OLD" -gt 90 ]; then
            WARNINGS+=("$ROOT_FILE last modified $DAYS_OLD days ago - may be stale")
        fi
    fi
fi

# Common exclusions
EXCLUSIONS="-not -path \"*/node_modules/*\" -not -path \"*/.git/*\" -not -path \"*/dist/*\" -not -path \"*/build/*\" -not -path \"*/public/*\" -not -path \"*/target/*\" -not -path \"*/.turbo/*\" -not -path \"*/vendor/*\""

# Find child AGENTS.md files (excluding root)
while IFS= read -r file; do
    if [ -n "$file" ]; then
        CHILD_NODES+=("$file")
    fi
done < <(eval "find \"$TARGET_PATH\" -name \"AGENTS.md\" -not -path \"$TARGET_PATH/AGENTS.md\" $EXCLUSIONS 2>/dev/null")

# Find orphaned CLAUDE.md files in subdirectories (potential issues)
ORPHAN_CLAUDE=()
while IFS= read -r file; do
    if [ -n "$file" ] && [ "$file" != "$TARGET_PATH/CLAUDE.md" ]; then
        ORPHAN_CLAUDE+=("$file")
    fi
done < <(eval "find \"$TARGET_PATH\" -name \"CLAUDE.md\" -not -path \"$TARGET_PATH/CLAUDE.md\" $EXCLUSIONS 2>/dev/null")

if [ ${#ORPHAN_CLAUDE[@]} -gt 0 ]; then
    WARNINGS+=("Found CLAUDE.md in subdirectories (should be AGENTS.md): ${ORPHAN_CLAUDE[*]}")
fi

# Output state
echo "=== Intent Layer State ==="
echo "root_file: ${ROOT_FILE:-none}"
echo "has_intent_section: $HAS_INTENT_SECTION"
echo "child_nodes: ${#CHILD_NODES[@]}"

for node in "${CHILD_NODES[@]}"; do
    echo "  - $node"
done

# Show warnings if any
if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo ""
    echo "## Warnings"
    for warning in "${WARNINGS[@]}"; do
        echo "  ! $warning"
    done
fi

echo ""
if [ -z "$ROOT_FILE" ]; then
    echo "state: none"
    echo "action: Run intent-layer skill for initial setup"
elif [ "$HAS_INTENT_SECTION" = false ]; then
    echo "state: partial"
    echo "action: Add Intent Layer section to $ROOT_FILE"
else
    echo "state: complete"
    echo "action: Run intent-layer-maintenance skill for audits"
fi
