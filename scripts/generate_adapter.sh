#!/usr/bin/env bash
set -euo pipefail

# generate_adapter.sh - Export Intent Layer context to other AI coding tools
#
# Usage: generate_adapter.sh <project_root> [options]
#
# Exports the Intent Layer hierarchy (AGENTS.md/CLAUDE.md files) into formats
# consumable by other AI coding tools like Cursor.
#
# Arguments:
#   project_root       Path to the project root (where root CLAUDE.md lives)
#
# Options:
#   --format <name>    Output format: cursor, raw (default: cursor)
#   --max-tokens <n>   Token budget per node (default: 4000)
#   --output <path>    Write to file/directory (default: stdout for raw,
#                      .cursor/rules/ for cursor)
#   -h, --help         Show this help
#
# Formats:
#   cursor   Generate .cursor/rules/*.mdc files with YAML frontmatter.
#            One file per AGENTS.md node, root as intent-layer-root.mdc.
#            Stale .mdc files from previous runs are cleaned automatically.
#
#   raw      Flat merged markdown on stdout (or to --output file).
#            All nodes concatenated in hierarchy order (root first).
#
# Exit codes:
#   0 - Success
#   1 - Invalid input (bad args, missing project root)
#   2 - No Intent Layer found in project
#
# Examples:
#   generate_adapter.sh /path/to/project
#   generate_adapter.sh /path/to/project --format raw
#   generate_adapter.sh /path/to/project --format cursor --output ./out/rules/
#   generate_adapter.sh /path/to/project --max-tokens 2000

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Defaults
FORMAT="cursor"
MAX_TOKENS=4000
OUTPUT=""

POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --format)
            if [[ $# -lt 2 ]]; then
                echo "Error: --format requires an argument" >&2
                exit 1
            fi
            FORMAT="$2"; shift 2 ;;
        --max-tokens)
            if [[ $# -lt 2 ]]; then
                echo "Error: --max-tokens requires an argument" >&2
                exit 1
            fi
            MAX_TOKENS="$2"; shift 2 ;;
        --output)
            if [[ $# -lt 2 ]]; then
                echo "Error: --output requires an argument" >&2
                exit 1
            fi
            OUTPUT="$2"; shift 2 ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done
set -- "${POSITIONAL[@]+"${POSITIONAL[@]}"}"

# Validate format
if [[ "$FORMAT" != "cursor" && "$FORMAT" != "raw" ]]; then
    echo "Error: Unknown format '$FORMAT'. Supported: cursor, raw" >&2
    exit 1
fi

# Validate max-tokens is a number
if ! [[ "$MAX_TOKENS" =~ ^[0-9]+$ ]]; then
    echo "Error: --max-tokens must be a positive integer, got '$MAX_TOKENS'" >&2
    exit 1
fi

# Require project root
if [[ $# -lt 1 ]]; then
    echo "Error: Missing required argument: project_root" >&2
    echo "Usage: generate_adapter.sh <project_root> [options]" >&2
    exit 1
fi

PROJECT_ROOT="$1"

if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Error: Project root not found: $PROJECT_ROOT" >&2
    exit 1
fi

PROJECT_ROOT=$(cd "$PROJECT_ROOT" && pwd)

# --- Detect Intent Layer ---

ROOT_FILE=""
if [[ -f "$PROJECT_ROOT/CLAUDE.md" ]]; then
    ROOT_FILE="$PROJECT_ROOT/CLAUDE.md"
elif [[ -f "$PROJECT_ROOT/AGENTS.md" ]]; then
    ROOT_FILE="$PROJECT_ROOT/AGENTS.md"
fi

if [[ -z "$ROOT_FILE" ]]; then
    echo "Error: No Intent Layer found in $PROJECT_ROOT" >&2
    echo "No CLAUDE.md or AGENTS.md at project root." >&2
    echo "Run /intent-layer to set up." >&2
    exit 2
fi

# --- Find all nodes (root + children) ---

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

ALL_NODES=()
ALL_NODES+=("$ROOT_FILE")

while IFS= read -r file; do
    if [[ -n "$file" && "$file" != "$PROJECT_ROOT/AGENTS.md" ]]; then
        ALL_NODES+=("$file")
    fi
done < <(find "$PROJECT_ROOT" -name "AGENTS.md" \
    -not -path "$PROJECT_ROOT/AGENTS.md" \
    "${FIND_EXCLUSIONS[@]}" 2>/dev/null | sort)

# --- Token budget helpers ---

# Effective budget = 80% of max (safety margin)
EFFECTIVE_BUDGET=$(( MAX_TOKENS * 80 / 100 ))

estimate_tokens() {
    local text="$1"
    local bytes
    bytes=$(printf '%s' "$text" | wc -c | tr -d ' ')
    echo $(( bytes / 4 ))
}

# Drop sections in priority order (lowest priority first):
# Entry Points > Patterns > Pitfalls > Contracts
# Returns trimmed content that fits within the token budget.
trim_to_budget() {
    local content="$1"
    local budget="$2"
    local tokens
    tokens=$(estimate_tokens "$content")

    if [[ "$tokens" -le "$budget" ]]; then
        echo "$content"
        return
    fi

    # Sections to drop, lowest priority first
    local drop_order=("Entry Points" "Patterns" "Pitfalls" "Contracts")

    for section_name in "${drop_order[@]}"; do
        # Remove section: from ## <name> to next ## at same or higher level
        content=$(echo "$content" | awk -v section="$section_name" '
            BEGIN { skip = 0; level = 0 }
            /^##+ / {
                if (skip) {
                    match($0, /^#+/)
                    current_level = RLENGTH
                    if (current_level <= level) {
                        skip = 0
                    }
                }
                if (!skip) {
                    # Build pattern: ## followed by section name (case insensitive)
                    line = tolower($0)
                    target = tolower(section)
                    if (line ~ "^##+ *" target "$") {
                        skip = 1
                        match($0, /^#+/)
                        level = RLENGTH
                        next
                    }
                }
            }
            !skip { print }
        ')

        tokens=$(estimate_tokens "$content")
        echo "Warning: Dropped section '$section_name' to fit token budget ($tokens/$budget tokens)" >&2

        if [[ "$tokens" -le "$budget" ]]; then
            break
        fi
    done

    echo "$content"
}

# --- Generate node slug for .mdc filename ---

node_slug() {
    local node_path="$1"
    local rel="${node_path#$PROJECT_ROOT/}"

    if [[ "$node_path" == "$ROOT_FILE" ]]; then
        echo "intent-layer-root"
        return
    fi

    # Turn path like src/api/AGENTS.md into intent-layer-src-api
    local dir
    dir=$(dirname "$rel")
    echo "intent-layer-${dir//\//-}"
}

# --- Generate glob pattern for a node ---

node_globs() {
    local node_path="$1"

    if [[ "$node_path" == "$ROOT_FILE" ]]; then
        # Root applies to everything
        echo ""
        return
    fi

    local rel="${node_path#$PROJECT_ROOT/}"
    local dir
    dir=$(dirname "$rel")
    echo "${dir}/**"
}

# --- Format: cursor ---

generate_cursor() {
    local output_dir="$OUTPUT"
    if [[ -z "$output_dir" ]]; then
        output_dir="$PROJECT_ROOT/.cursor/rules"
    fi

    mkdir -p "$output_dir"

    # Track which .mdc files we generate (for stale cleanup)
    local generated_files=()

    for node in "${ALL_NODES[@]}"; do
        local slug
        slug=$(node_slug "$node")
        local mdc_file="$output_dir/${slug}.mdc"
        generated_files+=("$mdc_file")

        local content
        content=$(cat "$node")

        # Trim to budget
        content=$(trim_to_budget "$content" "$EFFECTIVE_BUDGET")

        # Remove empty lines at start/end (portable across BSD and GNU)
        content=$(echo "$content" | awk '
            NF { found=1 }
            found { lines[++n] = $0 }
            END {
                # Trim trailing empty lines
                while (n > 0 && lines[n] == "") n--
                for (i = 1; i <= n; i++) print lines[i]
            }
        ')

        # Build frontmatter
        local is_root=false
        [[ "$node" == "$ROOT_FILE" ]] && is_root=true

        local globs
        globs=$(node_globs "$node")

        local rel_node="${node#$PROJECT_ROOT/}"
        local description="Intent Layer context from $rel_node"

        {
            echo "---"
            echo "description: \"$description\""
            if [[ -n "$globs" ]]; then
                echo "globs: \"$globs\""
            fi
            if [[ "$is_root" == "true" ]]; then
                echo "alwaysApply: true"
            else
                echo "alwaysApply: false"
            fi
            echo "---"
            echo ""
            echo "$content"
        } > "$mdc_file"
    done

    # Clean stale .mdc files from previous runs
    # Only remove intent-layer-*.mdc files that we didn't just generate
    while IFS= read -r existing; do
        [[ -z "$existing" ]] && continue
        local is_stale=true
        for gen in "${generated_files[@]}"; do
            if [[ "$existing" == "$gen" ]]; then
                is_stale=false
                break
            fi
        done
        if [[ "$is_stale" == "true" ]]; then
            rm -f "$existing"
            echo "Removed stale: $(basename "$existing")" >&2
        fi
    done < <(find "$output_dir" -name "intent-layer-*.mdc" -type f 2>/dev/null)

    echo "Generated ${#ALL_NODES[@]} .mdc file(s) in $output_dir" >&2
}

# --- Format: raw ---

generate_raw() {
    local output_text=""

    for node in "${ALL_NODES[@]}"; do
        local content
        content=$(cat "$node")

        # Trim to budget
        content=$(trim_to_budget "$content" "$EFFECTIVE_BUDGET")

        local rel_node="${node#$PROJECT_ROOT/}"

        if [[ -n "$output_text" ]]; then
            output_text="$output_text

---

<!-- Source: $rel_node -->

$content"
        else
            output_text="<!-- Source: $rel_node -->

$content"
        fi
    done

    if [[ -n "$OUTPUT" ]]; then
        # Create parent directory if needed
        mkdir -p "$(dirname "$OUTPUT")"
        echo "$output_text" > "$OUTPUT"
        echo "Written to $OUTPUT" >&2
    else
        echo "$output_text"
    fi
}

# --- Main ---

case "$FORMAT" in
    cursor) generate_cursor ;;
    raw) generate_raw ;;
esac
