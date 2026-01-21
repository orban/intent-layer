#!/usr/bin/env bash
# Analyze codebase structure for Intent Layer placement
# Usage: ./analyze_structure.sh [path]

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
analyze_structure.sh - Analyze codebase structure for Intent Layer placement

USAGE:
    analyze_structure.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    -h, --help    Show this help message

OUTPUT:
    - Directory structure (depth 3)
    - Existing Intent Nodes
    - Large directories (potential semantic boundaries)
    - Package/config files (standalone subsystems)
    - Suggested Intent Node locations

EXAMPLES:
    analyze_structure.sh                    # Analyze current directory
    analyze_structure.sh /path/to/project   # Analyze specific project
    analyze_structure.sh ~/monorepo         # Analyze monorepo
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
    exit 1
fi

if [ ! -r "$TARGET_PATH" ]; then
    echo "❌ Error: Permission denied reading: $TARGET_PATH" >&2
    exit 1
fi

# Resolve to absolute path for cleaner output
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

echo "=== Intent Layer Structure Analysis ==="
echo "Target: $TARGET_PATH"
echo ""

# Common exclusions for generated/dependency directories
EXCLUSIONS=(
  "*/node_modules/*"
  "*/.git/*"
  "*/dist/*"
  "*/.next/*"
  "*/build/*"
  "*/__pycache__/*"
  "*/public/*"           # Hugo, static site generators
  "*/resources/_gen/*"   # Hugo generated
  "*/.turbo/*"           # Turborepo cache
  "*/coverage/*"         # Test coverage
  "*/target/*"           # Rust/Cargo
  "*/vendor/*"           # Go vendor, PHP composer
  "*/.venv/*"            # Python virtual env
  "*/venv/*"             # Python virtual env
  "*/.cache/*"           # Various caches
  "*/out/*"              # Next.js output
)

# Build find exclusion arguments
FIND_EXCLUDES=""
for pattern in "${EXCLUSIONS[@]}"; do
  FIND_EXCLUDES="$FIND_EXCLUDES -not -path \"$pattern\""
done

echo "## Directory Structure (depth 3)"
eval "find \"$TARGET_PATH\" -type d -maxdepth 3 $FIND_EXCLUDES" 2>/dev/null | head -50 || true

echo ""
echo "## Existing Intent Nodes"
EXISTING_NODES=$(find "$TARGET_PATH" \( -name "AGENTS.md" -o -name "CLAUDE.md" \) 2>/dev/null | head -20) || true
if [ -n "$EXISTING_NODES" ]; then
  echo "$EXISTING_NODES"
else
  echo "(none found)"
fi

# Detect root context file
ROOT_FILE=""
if [ -f "$TARGET_PATH/CLAUDE.md" ]; then
  ROOT_FILE="CLAUDE.md"
elif [ -f "$TARGET_PATH/AGENTS.md" ]; then
  ROOT_FILE="AGENTS.md"
fi

echo ""
echo "## Large Directories (potential boundaries)"
echo "(Directories with >20 files, excluding generated paths)"
eval "find \"$TARGET_PATH\" -type d $FIND_EXCLUDES" 2>/dev/null | while read -r dir; do
  count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ') || count=0
  if [ "$count" -gt 20 ]; then
    echo "$count files: $dir"
  fi
done | sort -rn | head -15 || true

echo ""
echo "## Package/Config Files (semantic boundaries)"
echo "(Standalone subsystems with their own package manager)"
eval "find \"$TARGET_PATH\" -maxdepth 4 \( -name \"package.json\" -o -name \"Cargo.toml\" -o -name \"go.mod\" -o -name \"pyproject.toml\" \) $FIND_EXCLUDES" 2>/dev/null | head -20 || true

echo ""
echo "## Suggested Intent Node Locations"
if [ -n "$ROOT_FILE" ]; then
  echo "1. Root: $TARGET_PATH/$ROOT_FILE (exists)"
else
  echo "1. Root: $TARGET_PATH/{CLAUDE.md or AGENTS.md} (create one - not both)"
fi

# Find src-like directories
COUNTER=2
for dir in src lib app packages services api cmd internal; do
  if [ -d "$TARGET_PATH/$dir" ]; then
    echo "$COUNTER. Source: $TARGET_PATH/$dir/AGENTS.md"
    COUNTER=$((COUNTER + 1))
  fi
done

echo ""
echo "## Exclusions Applied"
echo "Skipped: node_modules, .git, dist, build, public, resources/_gen, .turbo,"
echo "         coverage, target, vendor, .venv, venv, .cache, out, .next"
echo ""
echo "Run estimate_tokens.sh on specific directories to determine if they need their own node."
