#!/usr/bin/env bash
# Estimate tokens for all candidate directories in a project
# Usage: ./estimate_all_candidates.sh [path]
#
# Automatically discovers semantic boundaries (src, lib, api, etc.)
# and produces a consolidated table with recommendations.

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
estimate_all_candidates.sh - Analyze token distribution across project

USAGE:
    estimate_all_candidates.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    -h, --help    Show this help message

OUTPUT:
    Table of directories with token estimates and recommendations:
    - <20k tokens: No Intent Node needed
    - 20-64k tokens: Good candidate for AGENTS.md
    - >64k tokens: Consider splitting into child nodes

EXAMPLES:
    estimate_all_candidates.sh                    # Analyze current directory
    estimate_all_candidates.sh /path/to/project   # Analyze specific project
    estimate_all_candidates.sh ~/my-monorepo      # Analyze monorepo
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

# Validate path
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

TARGET_PATH=$(cd "$TARGET_PATH" && pwd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Intent Layer Token Analysis ==="
echo "Target: $TARGET_PATH"
echo ""

# Common exclusions
EXCLUSIONS=(
    "*/node_modules/*" "*/.git/*" "*/dist/*" "*/.next/*" "*/build/*"
    "*/__pycache__/*" "*/public/*" "*/resources/_gen/*" "*/.turbo/*"
    "*/coverage/*" "*/target/*" "*/vendor/*" "*/.venv/*" "*/venv/*"
    "*/.cache/*" "*/out/*" "*/.worktrees/*"
)

FIND_EXCLUDES=""
for pattern in "${EXCLUSIONS[@]}"; do
    FIND_EXCLUDES="$FIND_EXCLUDES -not -path \"$pattern\""
done

# File patterns for token counting
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

# Function to estimate tokens for a directory
estimate_dir() {
    local dir="$1"
    local bytes
    bytes=$(eval "find \"$dir\" -type f $FILE_PATTERNS $FIND_EXCLUDES -exec cat {} + 2>/dev/null" | wc -c | tr -d ' ') || bytes=0
    echo $((bytes / 4))
}

# Function to format token count
format_tokens() {
    local tokens="$1"
    if ! [[ "$tokens" =~ ^[0-9]+$ ]]; then
        echo "0"
        return
    fi
    if [ "$tokens" -ge 1000000 ]; then
        echo "$(echo "scale=1; $tokens/1000000" | bc 2>/dev/null || echo "$tokens")M"
    elif [ "$tokens" -ge 1000 ]; then
        echo "$(echo "scale=1; $tokens/1000" | bc 2>/dev/null || echo "$tokens")k"
    else
        echo "$tokens"
    fi
}

# Collect candidates
declare -a CANDIDATES
declare -A TOKENS
declare -A DECISIONS

# Always include root
CANDIDATES+=("$TARGET_PATH")

# Find standard source directories
for dir in src lib app packages services api cmd internal core utils components modules; do
    if [ -d "$TARGET_PATH/$dir" ]; then
        CANDIDATES+=("$TARGET_PATH/$dir")
    fi
done

# Find directories with package managers (semantic boundaries)
while IFS= read -r pkg_file; do
    if [ -n "$pkg_file" ]; then
        dir=$(dirname "$pkg_file")
        # Don't add root twice
        if [ "$dir" != "$TARGET_PATH" ]; then
            # Check if not already in candidates
            found=0
            for c in "${CANDIDATES[@]}"; do
                if [ "$c" = "$dir" ]; then
                    found=1
                    break
                fi
            done
            if [ "$found" -eq 0 ]; then
                CANDIDATES+=("$dir")
            fi
        fi
    fi
done < <(eval "find \"$TARGET_PATH\" -maxdepth 3 \( -name \"package.json\" -o -name \"Cargo.toml\" -o -name \"go.mod\" -o -name \"pyproject.toml\" \) $FIND_EXCLUDES 2>/dev/null" || true)

# Find large directories (>50 files)
while IFS= read -r dir; do
    if [ -n "$dir" ] && [ "$dir" != "$TARGET_PATH" ]; then
        count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ') || count=0
        if [ "$count" -gt 50 ]; then
            found=0
            for c in "${CANDIDATES[@]}"; do
                if [ "$c" = "$dir" ]; then
                    found=1
                    break
                fi
            done
            if [ "$found" -eq 0 ]; then
                CANDIDATES+=("$dir")
            fi
        fi
    fi
done < <(eval "find \"$TARGET_PATH\" -type d -maxdepth 2 $FIND_EXCLUDES 2>/dev/null" || true)

echo "## Token Estimates"
echo ""
printf "%-40s %10s %10s  %-30s\n" "Directory" "Tokens" "Threshold" "Recommendation"
printf "%-40s %10s %10s  %-30s\n" "----------------------------------------" "----------" "----------" "------------------------------"

# Process each candidate
for dir in "${CANDIDATES[@]}"; do
    tokens=$(estimate_dir "$dir")
    TOKENS["$dir"]=$tokens
    formatted=$(format_tokens "$tokens")

    # Shorten path for display
    short_path="${dir#$TARGET_PATH/}"
    if [ "$short_path" = "$dir" ]; then
        short_path="(root)"
    fi

    # Truncate if too long
    if [ ${#short_path} -gt 38 ]; then
        short_path="${short_path:0:35}..."
    fi

    # Determine threshold and recommendation
    if [ "$tokens" -lt 20000 ]; then
        threshold="<20k"
        decision="No node needed"
        DECISIONS["$dir"]="skip"
    elif [ "$tokens" -lt 64000 ]; then
        threshold="20-64k"
        decision="Good candidate for AGENTS.md"
        DECISIONS["$dir"]="create"
    else
        threshold=">64k"
        decision="Consider child nodes"
        DECISIONS["$dir"]="split"
    fi

    printf "%-40s %10s %10s  %-30s\n" "$short_path" "$formatted" "$threshold" "$decision"
done

echo ""

# Summary
create_count=0
split_count=0
for dir in "${CANDIDATES[@]}"; do
    case "${DECISIONS[$dir]:-}" in
        create) create_count=$((create_count + 1)) ;;
        split) split_count=$((split_count + 1)) ;;
    esac
done

echo "## Summary"
echo ""
echo "Candidates for AGENTS.md: $create_count"
echo "Candidates for splitting: $split_count"

if [ $create_count -gt 0 ] || [ $split_count -gt 0 ]; then
    echo ""
    echo "## Suggested Actions"
    echo ""
    for dir in "${CANDIDATES[@]}"; do
        short_path="${dir#$TARGET_PATH/}"
        if [ "$short_path" = "$dir" ]; then
            short_path="(root)"
        fi

        case "${DECISIONS[$dir]:-}" in
            create)
                if [ "$short_path" = "(root)" ]; then
                    echo "- Root: Ensure Intent Layer section exists in CLAUDE.md/AGENTS.md"
                else
                    echo "- $short_path/AGENTS.md: Create with 2-3k token summary"
                fi
                ;;
            split)
                if [ "$short_path" = "(root)" ]; then
                    echo "- Root: Large codebase - consider child nodes for major subsystems"
                else
                    echo "- $short_path: Consider splitting into child AGENTS.md files"
                fi
                ;;
        esac
    done
fi

echo ""
echo "## Exclusions Applied"
echo "Skipped: node_modules, .git, dist, build, public, resources/_gen, .turbo,"
echo "         coverage, target, vendor, .venv, venv, .cache, out, .next"
