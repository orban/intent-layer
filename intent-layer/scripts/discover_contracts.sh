#!/usr/bin/env bash
# Discover and map Intent Layer nodes and their contracts
# Usage: ./discover_contracts.sh [options] [path]
#
# Outputs JSON mapping of nodes, contracts, covered files, and complexity

set -euo pipefail

# Help message
show_help() {
    cat << 'EOF'
discover_contracts.sh - Mechanical discovery of Intent Layer nodes and contracts

USAGE:
    discover_contracts.sh [OPTIONS] [PATH]

ARGUMENTS:
    PATH    Directory to analyze (default: current directory)

OPTIONS:
    --scope changed|full    What files to check (default: changed)
    --base REF              Git ref for comparison (default: origin/main)
    --format json           Output format (default: json)
    -h, --help              Show this help message

OUTPUT (JSON):
    {
      "nodes": [
        {
          "path": "CLAUDE.md",
          "depth": 0,
          "parent": null,
          "contracts": ["..."],
          "contract_count": 6,
          "covered_files": ["file1.sh", "file2.sh"],
          "file_count": 2,
          "complexity": "low|medium|high",
          "recommended_model": "haiku|sonnet"
        }
      ],
      "tree": {
        "CLAUDE.md": ["child/AGENTS.md"]
      }
    }

COMPLEXITY HEURISTICS:
    low:    ≤3 contracts AND ≤5 files → recommend "haiku"
    medium: ≤6 contracts AND ≤15 files → recommend "sonnet"
    high:   >6 contracts OR >15 files OR contains "CRITICAL" → recommend "sonnet"

CONTRACT EXTRACTION:
    Lines matching: ^- .*(must|never|always|require) (case insensitive)
    from "### Contracts" sections in CLAUDE.md/AGENTS.md files.

EXAMPLES:
    discover_contracts.sh                          # Changed files vs origin/main
    discover_contracts.sh --scope full             # All files in repo
    discover_contracts.sh --base main --scope changed
    discover_contracts.sh /path/to/project
EOF
    exit 0
}

# Parse arguments
SCOPE="changed"
BASE_REF="origin/main"
FORMAT="json"
TARGET_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        --scope)
            if [[ -z "${2:-}" ]]; then
                echo "Error: --scope requires a value (changed|full)" >&2
                exit 1
            fi
            SCOPE="$2"
            if [[ "$SCOPE" != "changed" && "$SCOPE" != "full" ]]; then
                echo "Error: --scope must be 'changed' or 'full'" >&2
                exit 1
            fi
            shift 2
            ;;
        --base)
            if [[ -z "${2:-}" ]]; then
                echo "Error: --base requires a git ref value" >&2
                exit 1
            fi
            BASE_REF="$2"
            shift 2
            ;;
        --format)
            if [[ -z "${2:-}" ]]; then
                echo "Error: --format requires a value" >&2
                exit 1
            fi
            FORMAT="$2"
            if [[ "$FORMAT" != "json" ]]; then
                echo "Error: Only 'json' format is currently supported" >&2
                exit 1
            fi
            shift 2
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [[ -n "$TARGET_PATH" ]]; then
                echo "Error: Multiple paths specified" >&2
                exit 1
            fi
            TARGET_PATH="$1"
            shift
            ;;
    esac
done

TARGET_PATH="${TARGET_PATH:-.}"

# Validate path exists
if [[ ! -d "$TARGET_PATH" ]]; then
    echo "Error: Directory not found: $TARGET_PATH" >&2
    echo "" >&2
    echo "   Please check:" >&2
    echo "     - The path is spelled correctly" >&2
    echo "     - The directory exists" >&2
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

# Change to target directory
cd "$TARGET_PATH"

# Verify we're in a git repo
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "Error: Not in a git repository" >&2
    exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)

# Common exclusions for find
EXCLUSIONS=( -not -path "*/node_modules/*" -not -path "*/.git/*" -not -path "*/dist/*" -not -path "*/build/*" -not -path "*/public/*" -not -path "*/target/*" -not -path "*/.turbo/*" -not -path "*/vendor/*" -not -path "*/.venv/*" -not -path "*/venv/*" -not -path "*/.worktrees/*" )

# Find all Intent Layer nodes
find_all_nodes() {
    local nodes=()

    # Check for root CLAUDE.md or AGENTS.md
    if [[ -f "$TARGET_PATH/CLAUDE.md" ]]; then
        nodes+=("CLAUDE.md")
    elif [[ -f "$TARGET_PATH/AGENTS.md" ]]; then
        nodes+=("AGENTS.md")
    fi

    # Find child AGENTS.md files
    while IFS= read -r file; do
        if [[ -n "$file" ]]; then
            # Make path relative to TARGET_PATH
            local rel_path="${file#$TARGET_PATH/}"
            nodes+=("$rel_path")
        fi
    done < <(find "$TARGET_PATH" -name "AGENTS.md" "${EXCLUSIONS[@]}" ! -path "$TARGET_PATH/AGENTS.md" 2>/dev/null | sort)

    printf '%s\n' "${nodes[@]}"
}

# Extract contracts from a node file
extract_contracts() {
    local node_path="$1"
    local full_path="$TARGET_PATH/$node_path"

    if [[ ! -f "$full_path" ]]; then
        return
    fi

    # Extract only from Contracts section (between ### Contracts or ## Contracts and next section)
    # Then apply the pattern filter
    local in_contracts=false
    while IFS= read -r line; do
        # Check for Contracts section header
        if [[ "$line" =~ ^##[#]?[[:space:]]+Contracts ]]; then
            in_contracts=true
            continue
        fi
        # Check for next section header (stops extraction)
        if [[ "$in_contracts" == "true" ]] && [[ "$line" =~ ^##[#]? ]]; then
            break
        fi
        # Extract lines matching contract pattern while in Contracts section
        if [[ "$in_contracts" == "true" ]]; then
            if echo "$line" | grep -iE '^- .*(must|never|always|require)' >/dev/null 2>&1; then
                echo "$line"
            fi
        fi
    done < "$full_path"
}

# Check if content contains CRITICAL
has_critical() {
    local node_path="$1"
    local full_path="$TARGET_PATH/$node_path"

    if [[ ! -f "$full_path" ]]; then
        echo "false"
        return
    fi

    if grep -q "CRITICAL" "$full_path" 2>/dev/null; then
        echo "true"
    else
        echo "false"
    fi
}

# Get changed files based on scope
get_files_to_check() {
    if [[ "$SCOPE" == "full" ]]; then
        # Get all tracked files plus untracked files
        git ls-files 2>/dev/null || true
        git ls-files --others --exclude-standard 2>/dev/null || true
    else
        # Get changed files vs base ref
        if git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
            git diff --name-only "$BASE_REF" HEAD 2>/dev/null || true
        fi
        # Also include uncommitted changes (staged, unstaged, and untracked)
        git diff --name-only HEAD 2>/dev/null || true
        git diff --name-only --cached 2>/dev/null || true
        git ls-files --others --exclude-standard 2>/dev/null || true
    fi | sort -u | grep -v '^$' || true
}

# Find which node covers a given file
find_covering_node() {
    local file="$1"
    local dir
    dir=$(dirname "$file")

    while [[ "$dir" != "." && "$dir" != "/" ]]; do
        if [[ -f "$TARGET_PATH/$dir/AGENTS.md" ]]; then
            echo "$dir/AGENTS.md"
            return
        fi
        if [[ -f "$TARGET_PATH/$dir/CLAUDE.md" ]]; then
            echo "$dir/CLAUDE.md"
            return
        fi
        dir=$(dirname "$dir")
    done

    # Check root (prefer CLAUDE.md over AGENTS.md for consistency with find_all_nodes)
    if [[ -f "$TARGET_PATH/CLAUDE.md" ]]; then
        echo "CLAUDE.md"
    elif [[ -f "$TARGET_PATH/AGENTS.md" ]]; then
        echo "AGENTS.md"
    fi
}

# Calculate node depth (number of directory levels)
get_node_depth() {
    local node_path="$1"
    local dir
    dir=$(dirname "$node_path")

    if [[ "$dir" == "." ]]; then
        echo 0
    else
        # Count slashes + 1 for the base directory level
        local slashes
        slashes=$(echo "$dir" | tr -cd '/' | wc -c | tr -d ' ')
        echo $((slashes + 1))
    fi
}

# Find parent node for a given node
find_parent_node() {
    local node_path="$1"
    local node_dir
    node_dir=$(dirname "$node_path")

    if [[ "$node_dir" == "." ]]; then
        echo "null"
        return
    fi

    # Go up directories looking for parent node
    local parent_dir
    parent_dir=$(dirname "$node_dir")

    while [[ "$parent_dir" != "." && "$parent_dir" != "/" ]]; do
        if [[ -f "$TARGET_PATH/$parent_dir/AGENTS.md" ]]; then
            echo "$parent_dir/AGENTS.md"
            return
        fi
        if [[ -f "$TARGET_PATH/$parent_dir/CLAUDE.md" ]]; then
            echo "$parent_dir/CLAUDE.md"
            return
        fi
        parent_dir=$(dirname "$parent_dir")
    done

    # Check root (prefer CLAUDE.md for consistency with find_all_nodes)
    if [[ -f "$TARGET_PATH/CLAUDE.md" ]]; then
        echo "CLAUDE.md"
    elif [[ -f "$TARGET_PATH/AGENTS.md" ]]; then
        echo "AGENTS.md"
    else
        echo "null"
    fi
}

# Calculate complexity and recommended model
calculate_complexity() {
    local contract_count="$1"
    local file_count="$2"
    local has_crit="$3"

    if [[ "$has_crit" == "true" ]] || [[ "$contract_count" -gt 6 ]] || [[ "$file_count" -gt 15 ]]; then
        echo "high:sonnet"
    elif [[ "$contract_count" -le 3 ]] && [[ "$file_count" -le 5 ]]; then
        echo "low:haiku"
    else
        echo "medium:sonnet"
    fi
}

# JSON escape a string
json_escape() {
    local str="$1"
    # Escape backslashes, double quotes, and control characters
    printf '%s' "$str" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g' | tr '\n' ' '
}

# Build JSON output
build_json() {
    local nodes_array="$1"
    local files_to_check="$2"

    # Start JSON
    echo "{"
    echo '  "nodes": ['

    local first_node=true
    local -A tree_map  # parent -> children

    while IFS= read -r node; do
        [[ -z "$node" ]] && continue

        # Get contracts
        local contracts_raw
        contracts_raw=$(extract_contracts "$node")

        local contract_count=0
        local contracts_json="["
        local first_contract=true

        while IFS= read -r contract; do
            [[ -z "$contract" ]] && continue
            contract_count=$((contract_count + 1))
            local escaped_contract
            escaped_contract=$(json_escape "$contract")
            if [[ "$first_contract" == "true" ]]; then
                first_contract=false
            else
                contracts_json+=", "
            fi
            contracts_json+="\"$escaped_contract\""
        done <<< "$contracts_raw"
        contracts_json+="]"

        # Get covered files
        local covered_files=()
        local node_dir
        node_dir=$(dirname "$node")
        [[ "$node_dir" == "." ]] && node_dir=""

        while IFS= read -r file; do
            [[ -z "$file" ]] && continue
            # Skip Intent Layer files themselves
            [[ "$file" == *"AGENTS.md" || "$file" == *"CLAUDE.md" ]] && continue

            local covering_node
            covering_node=$(find_covering_node "$file")
            if [[ "$covering_node" == "$node" ]]; then
                covered_files+=("$file")
            fi
        done <<< "$files_to_check"

        local file_count=${#covered_files[@]}

        # Build covered_files JSON array
        local covered_json="["
        local first_file=true
        for cf in "${covered_files[@]}"; do
            if [[ "$first_file" == "true" ]]; then
                first_file=false
            else
                covered_json+=", "
            fi
            covered_json+="\"$cf\""
        done
        covered_json+="]"

        # Calculate depth
        local depth
        depth=$(get_node_depth "$node")

        # Find parent
        local parent
        parent=$(find_parent_node "$node")

        # Track tree structure
        if [[ "$parent" != "null" ]]; then
            if [[ -z "${tree_map[$parent]:-}" ]]; then
                tree_map[$parent]="$node"
            else
                tree_map[$parent]="${tree_map[$parent]}|$node"
            fi
        fi

        # Check for CRITICAL
        local has_crit
        has_crit=$(has_critical "$node")

        # Calculate complexity
        local complexity_result
        complexity_result=$(calculate_complexity "$contract_count" "$file_count" "$has_crit")
        local complexity="${complexity_result%%:*}"
        local recommended_model="${complexity_result##*:}"

        # Format parent as JSON
        local parent_json
        if [[ "$parent" == "null" ]]; then
            parent_json="null"
        else
            parent_json="\"$parent\""
        fi

        # Output node JSON
        if [[ "$first_node" == "true" ]]; then
            first_node=false
        else
            echo ","
        fi

        cat << NODEJSON
    {
      "path": "$node",
      "depth": $depth,
      "parent": $parent_json,
      "contracts": $contracts_json,
      "contract_count": $contract_count,
      "covered_files": $covered_json,
      "file_count": $file_count,
      "complexity": "$complexity",
      "recommended_model": "$recommended_model"
    }
NODEJSON

    done <<< "$nodes_array"

    echo ""
    echo "  ],"

    # Build tree structure
    echo '  "tree": {'
    local first_tree=true

    # For each node that has children
    while IFS= read -r node; do
        [[ -z "$node" ]] && continue

        local children="${tree_map[$node]:-}"

        # Build children array from tree_map or from detected children
        local children_json="["
        local first_child=true

        if [[ -n "$children" ]]; then
            # Parse pipe-separated children
            IFS='|' read -ra child_array <<< "$children"
            for child in "${child_array[@]}"; do
                if [[ "$first_child" == "true" ]]; then
                    first_child=false
                else
                    children_json+=", "
                fi
                children_json+="\"$child\""
            done
        fi
        children_json+="]"

        if [[ "$first_tree" == "true" ]]; then
            first_tree=false
        else
            echo ","
        fi
        echo -n "    \"$node\": $children_json"

    done <<< "$nodes_array"

    echo ""
    echo "  }"
    echo "}"
}

# Main execution
main() {
    local nodes_array
    nodes_array=$(find_all_nodes)

    if [[ -z "$nodes_array" ]]; then
        # No nodes found - output empty structure
        cat << 'EMPTYJSON'
{
  "nodes": [],
  "tree": {}
}
EMPTYJSON
        exit 0
    fi

    local files_to_check
    files_to_check=$(get_files_to_check)

    build_json "$nodes_array" "$files_to_check"
}

main
