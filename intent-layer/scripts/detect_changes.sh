#!/usr/bin/env bash
# Detect which Intent Nodes are affected by code changes
# Usage: ./detect_changes.sh [base_ref] [head_ref]
#
# Examples:
#   ./detect_changes.sh main HEAD        # Changes on current branch vs main
#   ./detect_changes.sh HEAD~5 HEAD      # Last 5 commits
#   ./detect_changes.sh                  # Uncommitted changes (staged + unstaged)
#
# Output: List of affected Intent Nodes in leaf-first order for review

set -e

BASE_REF="${1:-}"
HEAD_REF="${2:-HEAD}"

# Get repo root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
    echo "Error: Not in a git repository"
    exit 1
fi

cd "$REPO_ROOT"

echo "=== Intent Layer Change Detection ==="
echo ""

# Get changed files
if [ -z "$BASE_REF" ]; then
    # No base ref - show uncommitted changes
    echo "Mode: Uncommitted changes"
    CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null; git diff --name-only --cached 2>/dev/null)
else
    echo "Mode: $BASE_REF..$HEAD_REF"
    CHANGED_FILES=$(git diff --name-only "$BASE_REF" "$HEAD_REF" 2>/dev/null)
fi

if [ -z "$CHANGED_FILES" ]; then
    echo ""
    echo "No changed files detected."
    exit 0
fi

# Count changed files
FILE_COUNT=$(echo "$CHANGED_FILES" | grep -v '^$' | wc -l | tr -d ' ')
echo "Changed files: $FILE_COUNT"
echo ""

# Find all Intent Nodes in repo
INTENT_NODES=$(find . -name "AGENTS.md" -o -name "CLAUDE.md" 2>/dev/null | sed 's|^\./||' | sort)

if [ -z "$INTENT_NODES" ]; then
    echo "No Intent Nodes found in repository."
    echo "Run intent-layer skill to set up Intent Layer."
    exit 0
fi

# Function to find covering Intent Node for a file
find_covering_node() {
    local file="$1"
    local dir=$(dirname "$file")

    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
        if [ -f "$dir/AGENTS.md" ]; then
            echo "$dir/AGENTS.md"
            return
        fi
        if [ -f "$dir/CLAUDE.md" ]; then
            echo "$dir/CLAUDE.md"
            return
        fi
        dir=$(dirname "$dir")
    done

    # Check root
    if [ -f "AGENTS.md" ]; then
        echo "AGENTS.md"
    elif [ -f "CLAUDE.md" ]; then
        echo "CLAUDE.md"
    fi
}

# Map changed files to covering nodes
declare -A NODE_FILES
declare -A NODE_DEPTH

echo "## Affected Intent Nodes"
echo ""

while IFS= read -r file; do
    [ -z "$file" ] && continue

    # Skip Intent Nodes themselves (they're not "covered" by nodes)
    if [[ "$file" == *"AGENTS.md" ]] || [[ "$file" == *"CLAUDE.md" ]]; then
        continue
    fi

    node=$(find_covering_node "$file")
    if [ -n "$node" ]; then
        # Track files per node
        if [ -z "${NODE_FILES[$node]}" ]; then
            NODE_FILES[$node]="$file"
            # Calculate depth (number of slashes)
            NODE_DEPTH[$node]=$(echo "$node" | tr -cd '/' | wc -c | tr -d ' ')
        else
            NODE_FILES[$node]="${NODE_FILES[$node]}"$'\n'"$file"
        fi
    fi
done <<< "$CHANGED_FILES"

# Check if any Intent Nodes were directly modified
MODIFIED_NODES=""
while IFS= read -r file; do
    if [[ "$file" == *"AGENTS.md" ]] || [[ "$file" == *"CLAUDE.md" ]]; then
        MODIFIED_NODES="$MODIFIED_NODES$file"$'\n'
    fi
done <<< "$CHANGED_FILES"

if [ -n "$MODIFIED_NODES" ]; then
    echo "### Directly Modified Nodes"
    echo "$MODIFIED_NODES" | grep -v '^$' | while read -r node; do
        echo "  * $node"
    done
    echo ""
fi

if [ ${#NODE_FILES[@]} -eq 0 ]; then
    echo "No Intent Nodes cover the changed files."
    exit 0
fi

# Sort nodes by depth (deepest first = leaf-first)
echo "### Nodes Covering Changed Code"
echo ""
printf "%-50s %s\n" "Node" "Changed Files"
printf "%-50s %s\n" "--------------------------------------------------" "-------------"

for node in "${!NODE_FILES[@]}"; do
    file_count=$(echo "${NODE_FILES[$node]}" | grep -v '^$' | wc -l | tr -d ' ')
    printf "%-50s %s\n" "$node" "$file_count files"
done | sort -t'/' -k1 -rn

echo ""
echo "## Review Order (leaf-first)"
echo ""
echo "Review deepest nodes first, then work up to root:"
echo ""

# Sort by depth descending
REVIEW_ORDER=""
for node in "${!NODE_FILES[@]}"; do
    depth="${NODE_DEPTH[$node]}"
    REVIEW_ORDER="$REVIEW_ORDER$depth $node"$'\n'
done

COUNTER=1
echo "$REVIEW_ORDER" | sort -rn | while read -r depth node; do
    [ -z "$node" ] && continue
    file_count=$(echo "${NODE_FILES[$node]}" | grep -v '^$' | wc -l | tr -d ' ')
    echo "$COUNTER. $node ($file_count files)"
    COUNTER=$((COUNTER + 1))
done

echo ""
echo "## Next Steps"
echo ""
echo "For each affected node:"
echo "1. Review the diff for covered files"
echo "2. Check if behavior changed (not just formatting)"
echo "3. Update node if contracts/patterns/pitfalls changed"
echo "4. Use agent-feedback-protocol.md format for proposals"
