#!/usr/bin/env bash
# Detect Intent Layer state in a project
# Usage: ./detect_state.sh [path]
# Returns: "none" | "partial" | "complete"

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
detect_state.sh - Check Intent Layer state in a project

USAGE:
    detect_state.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to check (default: current directory)

OPTIONS:
    -h, --help    Show this help message

OUTPUT:
    state: none      No CLAUDE.md or AGENTS.md found
    state: partial   Root file exists but no Intent Layer section
    state: complete  Full Intent Layer setup detected

EXAMPLES:
    detect_state.sh                    # Check current directory
    detect_state.sh /path/to/project   # Check specific project
    detect_state.sh ~/my-repo          # Check home directory repo
EOF
    exit 0
}

# Parse arguments
case "${1:-}" in
    -h|--help)
        show_help
        ;;
esac

TARGET_PATH="${1:-.}"

# Validate path exists
if [ ! -d "$TARGET_PATH" ]; then
    echo "❌ Error: Directory not found: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Please check:" >&2
    echo "     • The path is spelled correctly" >&2
    echo "     • The directory exists" >&2
    echo "     • You have permission to access it" >&2
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

ROOT_FILE=""
HAS_INTENT_SECTION=false
CHILD_NODES=()
WARNINGS=()

# Find root context file (CLAUDE.md preferred over AGENTS.md)
if [ -f "$TARGET_PATH/CLAUDE.md" ]; then
    ROOT_FILE="CLAUDE.md"
    # Check if AGENTS.md also exists at root
    if [ -f "$TARGET_PATH/AGENTS.md" ]; then
        # Check if either is a symlink to the other (expected for cross-tool compatibility)
        if [ -L "$TARGET_PATH/AGENTS.md" ] || [ -L "$TARGET_PATH/CLAUDE.md" ]; then
            : # Symlink is fine - this is the recommended setup
        else
            WARNINGS+=("Both CLAUDE.md and AGENTS.md exist at root (not symlinked). Consider symlinking one to the other.")
        fi
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

    # Check file age (cross-platform: try macOS stat first, then Linux)
    if [ -r "$TARGET_PATH/$ROOT_FILE" ]; then
        FILE_MTIME=""
        # macOS uses -f %m, Linux uses -c %Y
        if FILE_MTIME=$(stat -f %m "$TARGET_PATH/$ROOT_FILE" 2>/dev/null); then
            : # macOS stat succeeded
        elif FILE_MTIME=$(stat -c %Y "$TARGET_PATH/$ROOT_FILE" 2>/dev/null); then
            : # Linux stat succeeded
        fi

        if [ -n "$FILE_MTIME" ]; then
            CURRENT_TIME=$(date +%s)
            DAYS_OLD=$(( (CURRENT_TIME - FILE_MTIME) / 86400 ))
            if [ "$DAYS_OLD" -gt 90 ]; then
                WARNINGS+=("$ROOT_FILE last modified $DAYS_OLD days ago - may be stale")
            fi
        fi
    fi
fi

# Common exclusions for find (as array to avoid eval injection)
FIND_EXCLUSIONS=(
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
)

# Find child AGENTS.md files (excluding root)
FIND_AGENTS_ARGS=(
    "$TARGET_PATH"
    -name "AGENTS.md"
    -not -path "$TARGET_PATH/AGENTS.md"
    "${FIND_EXCLUSIONS[@]}"
)

while IFS= read -r file; do
    if [ -n "$file" ]; then
        CHILD_NODES+=("$file")
    fi
done < <(find "${FIND_AGENTS_ARGS[@]}" 2>/dev/null || true)

# Find orphaned CLAUDE.md files in subdirectories (potential issues)
ORPHAN_CLAUDE=()
FIND_CLAUDE_ARGS=(
    "$TARGET_PATH"
    -name "CLAUDE.md"
    -not -path "$TARGET_PATH/CLAUDE.md"
    "${FIND_EXCLUSIONS[@]}"
)

while IFS= read -r file; do
    if [ -n "$file" ]; then
        ORPHAN_CLAUDE+=("$file")
    fi
done < <(find "${FIND_CLAUDE_ARGS[@]}" 2>/dev/null || true)

if [ ${#ORPHAN_CLAUDE[@]} -gt 0 ]; then
    WARNINGS+=("Found CLAUDE.md in subdirectories (should be AGENTS.md for cross-tool compatibility): ${ORPHAN_CLAUDE[*]}")
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
