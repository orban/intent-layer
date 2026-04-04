#!/usr/bin/env bash
# Shared functions for learning layer hooks
# Source this at the start of hook scripts
#
# NOTE: This file does not set `set -euo pipefail` because it is designed
# to be sourced by other scripts. Sourcing scripts should set their own
# shell options to avoid unexpected behavior.

# Get plugin root from CLAUDE_PLUGIN_ROOT or walk up from script
get_plugin_root() {
    if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
        echo "$CLAUDE_PLUGIN_ROOT"
        return 0
    fi

    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    local dir="$script_dir"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "$dir/.claude-plugin" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "$(dirname "$(dirname "$script_dir")")"
}

# Check for jq and provide helpful error
require_jq() {
    if ! command -v jq &>/dev/null; then
        echo "Error: jq is required but not installed." >&2
        echo "Install with: brew install jq (macOS) or apt install jq (Linux)" >&2
        exit 1
    fi
}

# Parse JSON safely with fallback
json_get() {
    local json="$1"
    local path="$2"
    local default="${3:-}"

    if command -v jq &>/dev/null; then
        local result
        result=$(echo "$json" | jq -r "$path // empty" 2>/dev/null)
        if [[ -n "$result" && "$result" != "null" ]]; then
            echo "$result"
        else
            echo "$default"
        fi
    else
        echo "$default"
    fi
}

# Cross-platform date arithmetic
date_days_ago() {
    local days="$1"
    if date -v-1d &>/dev/null 2>&1; then
        date -v-"${days}d" +%Y-%m-%d
    else
        date -d "$days days ago" +%Y-%m-%d
    fi
}

# Cross-platform file modification check
file_newer_than() {
    local file="$1"
    local cutoff_date="$2"

    local file_date
    if stat -f %Sm -t %Y-%m-%d "$file" &>/dev/null 2>&1; then
        file_date=$(stat -f %Sm -t %Y-%m-%d "$file")
    else
        file_date=$(stat -c %y "$file" 2>/dev/null | cut -d' ' -f1)
    fi

    [[ "$file_date" > "$cutoff_date" || "$file_date" == "$cutoff_date" ]]
}

# Output JSON for hook response (additionalContext pattern)
output_context() {
    local hook_event="$1"
    local context="$2"

    require_jq
    jq -n \
        --arg event "$hook_event" \
        --arg ctx "$context" \
        '{
            hookSpecificOutput: {
                hookEventName: $event,
                additionalContext: $ctx
            }
        }'
}

# Output JSON for blocking decision
output_block() {
    local reason="$1"

    require_jq
    jq -n --arg reason "$reason" '{decision: "block", reason: $reason}'
}

telemetry_root() {
    local project_root="${1:-${CLAUDE_PROJECT_DIR:-.}}"
    echo "$project_root/.intent-layer/hooks"
}

telemetry_enabled() {
    local project_root="${1:-${CLAUDE_PROJECT_DIR:-.}}"
    [[ -d "$project_root/.intent-layer" ]] || return 1
    [[ ! -f "$project_root/.intent-layer/disable-telemetry" ]]
}

rotate_log_if_needed() {
    local log_file="$1"
    local max_lines="${2:-1000}"
    local keep_lines="${3:-500}"

    [[ -f "$log_file" ]] || return 0

    local log_lines
    log_lines=$(wc -l < "$log_file" 2>/dev/null || echo 0)
    if [[ "${log_lines// /}" -gt "$max_lines" ]]; then
        tail -"$keep_lines" "$log_file" > "$log_file.tmp" && mv "$log_file.tmp" "$log_file"
    fi
}

append_injection_telemetry() {
    local project_root="$1"
    local tool_name="$2"
    local file_path="$3"
    local coverage_status="$4"
    local covering_node="$5"
    local injected_sections="$6"

    telemetry_enabled "$project_root" || return 0

    local log_dir log_file timestamp
    log_dir="$(telemetry_root "$project_root")"
    log_file="$log_dir/injections.log"
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$log_dir"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$timestamp" \
        "${tool_name:-unknown}" \
        "${file_path:-unknown}" \
        "${coverage_status:-unknown}" \
        "${covering_node:-None}" \
        "${injected_sections:-none}" >> "$log_file" 2>/dev/null || true
    rotate_log_if_needed "$log_file"
}

append_outcome_telemetry() {
    local project_root="$1"
    local tool_name="$2"
    local result="$3"
    local file_path="$4"
    local coverage_status="$5"
    local covering_node="$6"
    local detail="$7"

    telemetry_enabled "$project_root" || return 0

    local log_dir log_file timestamp
    log_dir="$(telemetry_root "$project_root")"
    log_file="$log_dir/outcomes.log"
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p "$log_dir"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$timestamp" \
        "${tool_name:-unknown}" \
        "${result:-unknown}" \
        "${file_path:-unknown}" \
        "${coverage_status:-unknown}" \
        "${covering_node:-None}" \
        "${detail:-none}" >> "$log_file" 2>/dev/null || true
    rotate_log_if_needed "$log_file"
}

# Calculate word overlap between two strings
# Returns percentage (0-100) of matching significant words
# Significant words are 3+ characters, lowercased, alphanumeric only
calculate_word_overlap() {
    local str1="$1"
    local str2="$2"

    # Extract significant words (3+ chars, lowercase, alphanumeric)
    local words1 words2
    words1=$(echo "$str1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '\n' | awk 'length >= 3' | sort -u)
    words2=$(echo "$str2" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '\n' | awk 'length >= 3' | sort -u)

    # Count words in each set
    local count1 count2
    count1=$(echo "$words1" | grep -c . 2>/dev/null || echo 0)
    count2=$(echo "$words2" | grep -c . 2>/dev/null || echo 0)

    # Handle empty cases
    if [[ "$count1" -eq 0 || "$count2" -eq 0 ]]; then
        echo "0"
        return
    fi

    # Count matching words
    local matches=0
    while IFS= read -r word; do
        [[ -z "$word" ]] && continue
        if echo "$words2" | grep -qx "$word" 2>/dev/null; then
            matches=$((matches + 1))
        fi
    done <<< "$words1"

    # Calculate overlap percentage based on smaller set
    local min_count
    if [[ "$count1" -lt "$count2" ]]; then
        min_count="$count1"
    else
        min_count="$count2"
    fi

    # Return percentage (integer)
    echo $(( (matches * 100) / min_count ))
}

# Extract entries from a specific section of an AGENTS.md file
# Returns each entry (starting with ###) as a block
extract_section_entries() {
    local file="$1"
    local section="$2"

    awk -v section="$section" '
        /^## / {
            if (in_section) exit
            if ($0 == "## " section) { in_section=1; next }
        }
        in_section && /^### / { print; in_entry=1; next }
        in_section && in_entry && /^### / { print; next }
        in_section && in_entry { print }
    ' "$file"
}
