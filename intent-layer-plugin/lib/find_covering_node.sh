#!/usr/bin/env bash
# Find the covering AGENTS.md node for a given file path
# Usage: find_covering_node.sh <file_path> [--section NAME]

set -euo pipefail

show_help() {
    cat << 'EOF'
find_covering_node.sh - Find nearest covering AGENTS.md

USAGE:
    find_covering_node.sh <file_path> [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -s, --section NAME   Extract specific section (e.g., Pitfalls)

OUTPUT:
    Path to covering AGENTS.md/CLAUDE.md, or empty if none found.
    With --section, outputs the section content instead.
EOF
    exit 0
}

FILE_PATH=""
SECTION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -s|--section) SECTION="$2"; shift 2 ;;
        *)
            if [[ -z "$FILE_PATH" ]]; then
                FILE_PATH="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$FILE_PATH" ]]; then
    echo "Error: File path required" >&2
    exit 1
fi

# Normalize to absolute path
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="${CLAUDE_PROJECT_DIR:-$(pwd)}/$FILE_PATH"
fi

# Start from file's directory
if [[ -d "$FILE_PATH" ]]; then
    CURRENT_DIR="$FILE_PATH"
else
    CURRENT_DIR="$(dirname "$FILE_PATH")"
fi

NODE_PATH=""

while [[ "$CURRENT_DIR" != "/" ]]; do
    if [[ -f "$CURRENT_DIR/AGENTS.md" ]]; then
        NODE_PATH="$CURRENT_DIR/AGENTS.md"
        break
    fi
    if [[ -f "$CURRENT_DIR/CLAUDE.md" ]]; then
        NODE_PATH="$CURRENT_DIR/CLAUDE.md"
        break
    fi
    if [[ -d "$CURRENT_DIR/.git" ]]; then
        break
    fi
    CURRENT_DIR="$(dirname "$CURRENT_DIR")"
done

if [[ -z "$NODE_PATH" ]]; then
    exit 0
fi

if [[ -n "$SECTION" ]]; then
    awk -v section="$SECTION" '
        /^## / {
            if (found) exit
            if ($0 ~ "^## .*"section) found=1
        }
        found { print }
    ' "$NODE_PATH"
else
    echo "$NODE_PATH"
fi
