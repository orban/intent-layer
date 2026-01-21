#!/usr/bin/env bash
# Estimate token count for a directory to determine Intent Node needs.
#
# Usage:
#     estimate_tokens.sh <path>
#
# Token estimation: ~4 chars per token (rough approximation, ±20%)
#
# Guidelines:
#     <20k tokens: Usually no dedicated node needed
#     20-64k tokens: Good candidate for 2-3k token node
#     >64k tokens: Consider splitting into child nodes

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
estimate_tokens.sh - Estimate token count for a directory

USAGE:
    estimate_tokens.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    -h, --help    Show this help message

OUTPUT:
    Token estimate with ±20% margin, file count, top contributors,
    and recommendation for Intent Node creation.

THRESHOLDS:
    <20k tokens:    No dedicated node needed
    20-64k tokens:  Good candidate for 2-3k token node
    >64k tokens:    Consider splitting into child nodes

EXAMPLES:
    estimate_tokens.sh                    # Analyze current directory
    estimate_tokens.sh src/               # Analyze src directory
    estimate_tokens.sh ~/project/api      # Analyze specific path
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

# Validate path is readable
if [ ! -r "$TARGET_PATH" ]; then
    echo "❌ Error: Permission denied reading: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Try: chmod +r \"$TARGET_PATH\"" >&2
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)
DIR_NAME=$(basename "$TARGET_PATH")

echo "=== Token Estimate: $DIR_NAME ==="
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

# Build exclusion arguments for find
FIND_EXCLUDES=""
for pattern in "${EXCLUSIONS[@]}"; do
  FIND_EXCLUDES="$FIND_EXCLUDES -not -path \"$pattern\""
done

# File extensions to include
FILE_PATTERNS="\( -name \"*.ts\" -o -name \"*.tsx\" -o -name \"*.js\" -o -name \"*.jsx\" \
    -o -name \"*.cjs\" -o -name \"*.mjs\" \
    -o -name \"*.py\" -o -name \"*.go\" -o -name \"*.rs\" -o -name \"*.java\" \
    -o -name \"*.rb\" -o -name \"*.php\" -o -name \"*.swift\" -o -name \"*.kt\" \
    -o -name \"*.c\" -o -name \"*.cpp\" -o -name \"*.h\" -o -name \"*.cs\" \
    -o -name \"*.vue\" -o -name \"*.svelte\" -o -name \"*.astro\" \
    -o -name \"*.md\" -o -name \"*.mdx\" -o -name \"*.json\" \
    -o -name \"*.yaml\" -o -name \"*.yml\" -o -name \"*.toml\" \
    -o -name \"*.sql\" -o -name \"*.graphql\" -o -name \"*.prisma\" \
    -o -name \"*.proto\" \)"

# Count bytes and estimate tokens
BYTES=$(eval "find \"$TARGET_PATH\" -type f $FILE_PATTERNS $FIND_EXCLUDES -exec cat {} + 2>/dev/null" | wc -c | tr -d ' ') || BYTES=0

# Handle case where no files matched
if [ "$BYTES" -eq 0 ]; then
    echo "⚠️  Warning: No matching source files found."
    echo ""
    echo "Checked extensions: ts, tsx, js, jsx, cjs, mjs, py, go, rs, java,"
    echo "                    rb, php, swift, kt, c, cpp, h, cs, vue, svelte,"
    echo "                    astro, md, mdx, json, yaml, yml, toml, sql,"
    echo "                    graphql, prisma, proto"
    echo ""
    echo "Excluded paths: node_modules, .git, dist, build, public, target,"
    echo "                resources/_gen, .turbo, coverage, vendor, venv, .cache, out"
    echo ""
    echo "This may indicate:"
    echo "  • Directory contains only unsupported file types"
    echo "  • All files are in excluded directories"
    echo "  • Permission issues reading files"
    exit 0
fi

TOKENS=$((BYTES / 4))
FILE_COUNT=$(eval "find \"$TARGET_PATH\" -type f $FILE_PATTERNS $FIND_EXCLUDES 2>/dev/null" | wc -l | tr -d ' ') || FILE_COUNT=0

# Format tokens with human-readable suffix
if [ "$TOKENS" -ge 1000000 ]; then
    FORMATTED=$(echo "scale=1; $TOKENS/1000000" | bc 2>/dev/null || echo "$TOKENS")M
elif [ "$TOKENS" -ge 1000 ]; then
    FORMATTED=$(echo "scale=1; $TOKENS/1000" | bc 2>/dev/null || echo "$TOKENS")k
else
    FORMATTED=$TOKENS
fi

# Calculate margin of error (±20%)
MARGIN=$((TOKENS / 5))
LOW=$((TOKENS - MARGIN))
HIGH=$((TOKENS + MARGIN))

echo "Total tokens: ~$FORMATTED ($TOKENS ±20%)"
echo "File count: $FILE_COUNT files"
echo ""

# Show top contributors if there are many files
if [ "$FILE_COUNT" -gt 10 ]; then
    echo "## Top Token Contributors"
    eval "find \"$TARGET_PATH\" -type f $FILE_PATTERNS $FIND_EXCLUDES -exec wc -c {} + 2>/dev/null" \
        | sort -rn \
        | head -6 \
        | tail -5 \
        | while read -r bytes file; do
            if [ -n "$bytes" ] && [ -n "$file" ] && [[ "$bytes" =~ ^[0-9]+$ ]]; then
                tokens=$((bytes / 4))
                if [ "$tokens" -ge 1000 ]; then
                    formatted=$(echo "scale=1; $tokens/1000" | bc 2>/dev/null || echo "$tokens")k
                else
                    formatted=$tokens
                fi
                # Shorten path for display
                short_file="${file#$TARGET_PATH/}"
                echo "  ~${formatted}: $short_file"
            fi
        done
    echo ""
fi

# Recommendation
echo "## Recommendation"
if [ "$HIGH" -lt 20000 ]; then
    echo "Threshold: <20k (confident)"
    echo "Action: No dedicated Intent Node needed"
elif [ "$LOW" -lt 20000 ] && [ "$HIGH" -ge 20000 ]; then
    echo "Threshold: ~20k (borderline)"
    echo "Action: May need Intent Node - review content complexity"
elif [ "$HIGH" -lt 64000 ]; then
    echo "Threshold: 20-64k"
    echo "Action: Good candidate for 2-3k token Intent Node"
elif [ "$LOW" -lt 64000 ] && [ "$HIGH" -ge 64000 ]; then
    echo "Threshold: ~64k (borderline)"
    echo "Action: Consider child nodes if content is diverse"
else
    echo "Threshold: >64k"
    echo "Action: Consider splitting into child Intent Nodes"
fi

echo ""
echo "## Exclusions Applied"
echo "Skipped: node_modules, .git, dist, build, public, resources/_gen, .turbo,"
echo "         coverage, target, vendor, .venv, venv, .cache, out, .next"
