#!/usr/bin/env bash
set -euo pipefail

# generate_orientation.sh - Generate onboarding orientation from Intent Layer
#
# Usage: generate_orientation.sh <target_path> [--format <format>] [--role <role>]
#
# Arguments:
#   target_path    Path to project with Intent Layer
#
# Options:
#   --format <fmt>   Output format: overview (default), full, checklist
#   --role <role>    Filter for role: frontend, backend, fullstack, devops
#   --output <file>  Write to file instead of stdout
#   -h, --help       Show this help message
#
# Examples:
#   generate_orientation.sh /path/to/project
#   generate_orientation.sh /path/to/project --format full
#   generate_orientation.sh /path/to/project --role backend --output onboarding.md

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Defaults
FORMAT="overview"
ROLE=""
OUTPUT=""

# Parse arguments
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --role)
            ROLE="$2"
            shift 2
            ;;
        --output)
            OUTPUT="$2"
            shift 2
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [[ $# -lt 1 ]]; then
    echo "Error: Missing target path" >&2
    echo "Usage: generate_orientation.sh <target_path>" >&2
    exit 1
fi

TARGET_PATH="$1"

if [[ ! -d "$TARGET_PATH" ]]; then
    echo "Error: Directory not found: $TARGET_PATH" >&2
    exit 1
fi

# Check Intent Layer state and warn if not complete
DETECT_SCRIPT="${DETECT_SCRIPT:-$HOME/.claude/skills/intent-layer/scripts/detect_state.sh}"
if [[ -x "$DETECT_SCRIPT" ]]; then
    STATE_OUTPUT=$("$DETECT_SCRIPT" "$TARGET_PATH" 2>/dev/null || true)
    STATE=$(echo "$STATE_OUTPUT" | grep "^state:" | cut -d' ' -f2)
    if [[ "$STATE" != "complete" ]]; then
        echo "⚠️  Warning: Intent Layer state is '$STATE' (not 'complete')" >&2
        echo "   Results may be incomplete. Run 'intent-layer' skill to set up properly." >&2
        echo "" >&2
    fi
fi

# Find root Intent Node
find_root_node() {
    if [[ -f "$TARGET_PATH/CLAUDE.md" ]]; then
        echo "$TARGET_PATH/CLAUDE.md"
    elif [[ -f "$TARGET_PATH/AGENTS.md" ]]; then
        echo "$TARGET_PATH/AGENTS.md"
    else
        echo ""
    fi
}

# Find all Intent Nodes
find_all_nodes() {
    find "$TARGET_PATH" \( -name "CLAUDE.md" -o -name "AGENTS.md" \) \
        -not -path "*/.git/*" \
        -not -path "*/node_modules/*" \
        -not -path "*/.claude/*" \
        2>/dev/null | sort
}

# Extract TL;DR from a file (tries multiple patterns)
extract_tldr() {
    local file="$1"
    local result=""

    # Try 1: Explicit TL;DR line
    result=$(grep -m1 -E "^>.*TL;DR" "$file" 2>/dev/null | sed 's/^> *//' | sed 's/\*\*TL;DR\*\*: *//' | sed 's/TL;DR: *//' || true)
    [[ -n "$result" ]] && echo "$result" && return

    # Try 2: First paragraph after "Architecture Overview" or "Overview" section
    result=$(awk '
        /^##+ .*(Architecture Overview|Overview)/ { found=1; next }
        found && /^[^#\n]/ && !/^[|-]/ { print; exit }
    ' "$file" 2>/dev/null | head -1 || true)
    [[ -n "$result" ]] && echo "$result" && return

    # Try 3: First paragraph after any H2 heading (skip empty lines)
    result=$(awk '
        /^## / { found=1; next }
        found && /^[A-Z]/ && !/^##/ { print; exit }
    ' "$file" 2>/dev/null | head -1 || true)
    [[ -n "$result" ]] && echo "$result" && return

    echo ""
}

# Extract a section from a file (single section name)
extract_section_single() {
    local file="$1"
    local section="$2"

    awk -v section="$section" '
        BEGIN { in_section = 0; level = 0 }
        /^##+ / {
            if (in_section) {
                match($0, /^#+/)
                current_level = RLENGTH
                if (current_level <= level) {
                    in_section = 0
                }
            }
            if (tolower($0) ~ tolower(section)) {
                in_section = 1
                match($0, /^#+/)
                level = RLENGTH
                next  # Skip the header itself
            }
        }
        in_section && !/^##+ / { print }
    ' "$file" | sed '/^$/d' | head -20
}

# Extract a section, trying multiple variant names
# Usage: extract_section <file> <canonical_name>
# Canonical names: contracts, pitfalls, entry_points
extract_section() {
    local file="$1"
    local canonical="$2"
    local result=""
    local variants=""

    case "$canonical" in
        contracts|Contracts)
            variants="Contracts Coding.Style Style.Guide Guidelines Rules Conventions Standards"
            ;;
        pitfalls|Pitfalls)
            variants="Pitfalls Common.Issues Gotchas Known.Issues Troubleshooting Issues.Fixes Caveats"
            ;;
        entry_points|"Entry Points")
            variants="Entry.Points Build.Test Development.Commands Getting.Started Quick.Start Commands Setup"
            ;;
        *)
            # Use as-is if not a known canonical name
            variants="$canonical"
            ;;
    esac

    for variant in $variants; do
        # Convert dots back to spaces for matching
        local search_term="${variant//./ }"
        result=$(extract_section_single "$file" "$search_term")
        if [[ -n "$result" ]]; then
            echo "$result"
            return
        fi
    done

    echo ""
}

# Extract project name from path
get_project_name() {
    basename "$TARGET_PATH"
}

# Count nodes
count_nodes() {
    find_all_nodes | wc -l | tr -d ' '
}

# Generate overview format
generate_overview() {
    local root_node
    root_node=$(find_root_node)

    if [[ -z "$root_node" ]]; then
        echo "Error: No Intent Layer found at $TARGET_PATH" >&2
        echo "Run 'intent-layer' skill to set one up." >&2
        exit 1
    fi

    local project_name
    project_name=$(get_project_name)

    local tldr
    tldr=$(extract_tldr "$root_node")

    echo "# $project_name Orientation"
    echo ""
    echo "Generated from Intent Layer on $(date '+%Y-%m-%d')"
    echo ""

    echo "## Overview"
    echo ""
    if [[ -n "$tldr" ]]; then
        echo "> $tldr"
    else
        echo "> (No TL;DR found in root node)"
    fi
    echo ""

    echo "## Structure"
    echo ""
    echo "This project has **$(count_nodes)** Intent Node(s):"
    echo ""
    echo '```'
    find_all_nodes | while IFS= read -r node; do
        local rel_path="${node#$TARGET_PATH/}"
        local node_tldr
        node_tldr=$(extract_tldr "$node")
        if [[ -n "$node_tldr" ]]; then
            echo "📄 $rel_path"
            echo "   $node_tldr"
        else
            echo "📄 $rel_path"
        fi
    done
    echo '```'
    echo ""

    echo "## Global Rules"
    echo ""
    local contracts
    contracts=$(extract_section "$root_node" "contracts")
    if [[ -n "$contracts" ]]; then
        echo "These rules apply everywhere:"
        echo ""
        echo "$contracts" | while IFS= read -r line; do
            echo "$line"
        done
    else
        echo "(No global contracts documented)"
    fi
    echo ""

    echo "## Common Pitfalls"
    echo ""
    local pitfalls
    pitfalls=$(extract_section "$root_node" "pitfalls")
    if [[ -n "$pitfalls" ]]; then
        echo "Watch out for:"
        echo ""
        echo "$pitfalls" | while IFS= read -r line; do
            echo "$line"
        done
    else
        echo "(No pitfalls documented)"
    fi
    echo ""

    echo "## Next Steps"
    echo ""
    echo "1. Read the full root node: \`$root_node\`"
    echo "2. Identify your area from Subsystem Boundaries"
    echo "3. Read that area's AGENTS.md"
    echo "4. Follow Entry Points to start coding"
    echo ""
}

# Generate full format
generate_full() {
    generate_overview

    echo "---"
    echo ""
    echo "## Subsystem Deep Dives"
    echo ""

    find_all_nodes | while IFS= read -r node; do
        local rel_path="${node#$TARGET_PATH/}"
        # Skip root
        [[ "$rel_path" == "CLAUDE.md" || "$rel_path" == "AGENTS.md" ]] && continue

        echo "### $rel_path"
        echo ""

        local tldr
        tldr=$(extract_tldr "$node")
        if [[ -n "$tldr" ]]; then
            echo "> $tldr"
            echo ""
        fi

        local entry_points
        entry_points=$(extract_section "$node" "entry_points")
        if [[ -n "$entry_points" ]]; then
            echo "**Entry Points:**"
            echo "$entry_points" | head -10
            echo ""
        fi

        local contracts
        contracts=$(extract_section "$node" "contracts")
        if [[ -n "$contracts" ]]; then
            echo "**Local Contracts:**"
            echo "$contracts" | head -10
            echo ""
        fi

        local pitfalls
        pitfalls=$(extract_section "$node" "pitfalls")
        if [[ -n "$pitfalls" ]]; then
            echo "**Pitfalls:**"
            echo "$pitfalls" | head -10
            echo ""
        fi

        echo "---"
        echo ""
    done
}

# Generate checklist format
generate_checklist() {
    local project_name
    project_name=$(get_project_name)

    echo "# $project_name Onboarding Checklist"
    echo ""
    echo "**Name:** _______________"
    echo "**Start Date:** _______________"
    echo "**Role:** _______________"
    echo ""

    echo "## Day 1"
    echo ""
    echo "- [ ] Read root CLAUDE.md/AGENTS.md completely"
    echo "- [ ] Run \`show_hierarchy.sh\` to visualize structure"
    echo "- [ ] Identify which subsystem I'll work in"
    echo "- [ ] Read my subsystem's AGENTS.md"
    echo "- [ ] Note any questions for team"
    echo ""

    echo "## Week 1"
    echo ""
    echo "- [ ] Complete first small task"
    echo "- [ ] Verify I followed all documented contracts"
    echo "- [ ] Read AGENTS.md for adjacent subsystems"
    echo "- [ ] Document any confusion as Intent Layer feedback"
    echo ""

    echo "## Understanding Check"
    echo ""
    echo "Can you answer these questions?"
    echo ""
    echo "1. What does this project do? (one sentence)"
    echo "   > _______________"
    echo ""
    echo "2. What are the major subsystems?"
    echo "   > _______________"
    echo ""
    echo "3. What global rules apply everywhere?"
    echo "   > _______________"
    echo ""
    echo "4. What common mistakes should you avoid?"
    echo "   > _______________"
    echo ""
    echo "5. Where would you start for your first task?"
    echo "   > _______________"
    echo ""

    echo "## Feedback"
    echo ""
    echo "What was missing or confusing in the Intent Layer?"
    echo ""
    echo "| Type | Location | Finding |"
    echo "|------|----------|---------|"
    echo "| | | |"
    echo "| | | |"
    echo "| | | |"
    echo ""
}

# Filter by role (simple keyword matching)
filter_by_role() {
    local content="$1"
    local role="$2"

    case "$role" in
        frontend)
            echo "$content" | grep -i -E "(frontend|ui|component|react|vue|angular|css|style)" || echo "$content"
            ;;
        backend)
            echo "$content" | grep -i -E "(backend|api|server|database|service|endpoint)" || echo "$content"
            ;;
        devops)
            echo "$content" | grep -i -E "(devops|infra|deploy|ci|cd|docker|kubernetes|terraform)" || echo "$content"
            ;;
        *)
            echo "$content"
            ;;
    esac
}

# Main
output=""
case "$FORMAT" in
    overview)
        output=$(generate_overview)
        ;;
    full)
        output=$(generate_full)
        ;;
    checklist)
        output=$(generate_checklist)
        ;;
    *)
        echo "Error: Unknown format: $FORMAT" >&2
        echo "Valid formats: overview, full, checklist" >&2
        exit 1
        ;;
esac

# Apply role filter if specified
if [[ -n "$ROLE" ]]; then
    output=$(filter_by_role "$output" "$ROLE")
fi

# Output
if [[ -n "$OUTPUT" ]]; then
    echo "$output" > "$OUTPUT"
    echo "Orientation written to: $OUTPUT" >&2
else
    echo "$output"
fi
