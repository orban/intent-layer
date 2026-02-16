#!/usr/bin/env bash
# Suggest AGENTS.md updates by analyzing git diffs with the Anthropic API
# Usage: ./suggest_updates.sh [base_ref] [head_ref] [options]
#
# Examples:
#   ./suggest_updates.sh main HEAD          # Suggest updates for current branch
#   ./suggest_updates.sh --dry-run          # Show affected nodes without API calls
#   ./suggest_updates.sh HEAD~5 HEAD        # Last 5 commits

set -euo pipefail

# --- Constants ---
MODEL="claude-haiku-4-5-20251001"
MAX_PARALLEL=5
MAX_DIFF_CHARS=10000
MAX_RETRIES=3
SENSITIVE_PATTERNS='\.env$|\.env\.|credentials\.json$|\.pem$|\.key$|\.secret$'

# --- Help ---
show_help() {
    cat << 'EOF'
suggest_updates.sh - AI-powered AGENTS.md update suggestions

USAGE:
    suggest_updates.sh [OPTIONS] [BASE_REF] [HEAD_REF]

ARGUMENTS:
    BASE_REF    Git ref to compare from (default: main)
    HEAD_REF    Git ref to compare to (default: HEAD)

OPTIONS:
    --dry-run    Show affected nodes without calling the API
    -h, --help   Show this help message

REQUIREMENTS:
    - curl and jq installed
    - ANTHROPIC_API_KEY environment variable (optional: dry-run without it)
    - detect_changes.sh (bundled)

MODES:
    With ANTHROPIC_API_KEY:   Calls Haiku API for structured suggestions
    Without ANTHROPIC_API_KEY: Dry-run mode (shows affected nodes only)

EXIT CODES:
    0    Success (or no changes)
    1    Invalid input (bad git refs, missing deps)
    2    No affected nodes

EXAMPLES:
    suggest_updates.sh                      # main..HEAD with API
    suggest_updates.sh --dry-run            # main..HEAD without API
    suggest_updates.sh v1.0.0 v2.0.0       # Between tags
    suggest_updates.sh HEAD~5 HEAD          # Last 5 commits
EOF
    exit 0
}

# --- Arg parsing ---
DRY_RUN=false
POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --dry-run) DRY_RUN=true; shift ;;
        -*) echo "Error: Unknown option: $1" >&2; echo "Run with --help for usage." >&2; exit 1 ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done

BASE_REF="${POSITIONAL[0]:-main}"
HEAD_REF="${POSITIONAL[1]:-HEAD}"

# --- Dependency checks ---
for cmd in curl jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: $cmd is required but not installed." >&2
        echo "Install with: brew install $cmd (macOS) or apt install $cmd (Linux)" >&2
        exit 1
    fi
done

# --- Locate detect_changes.sh ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT_CHANGES="$SCRIPT_DIR/detect_changes.sh"

if [[ ! -x "$DETECT_CHANGES" ]]; then
    echo "Error: detect_changes.sh not found at $DETECT_CHANGES" >&2
    echo "This script must be run from the intent-layer plugin's scripts/ directory." >&2
    exit 1
fi

# --- Validate git refs ---
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Error: Not in a git repository." >&2
    exit 1
}

cd "$REPO_ROOT"

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $BASE_REF" >&2
    echo "Check that the branch/tag/commit exists." >&2
    exit 1
fi

if ! git rev-parse --verify "$HEAD_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $HEAD_REF" >&2
    echo "Check that the branch/tag/commit exists." >&2
    exit 1
fi

# --- Run detect_changes.sh and parse output ---
DETECT_EXIT=0
DETECT_OUTPUT=$("$DETECT_CHANGES" "$BASE_REF" "$HEAD_REF" 2>&1) || DETECT_EXIT=$?

if [[ $DETECT_EXIT -ne 0 ]]; then
    echo "Error: detect_changes.sh failed (exit $DETECT_EXIT)." >&2
    echo "$DETECT_OUTPUT" >&2
    exit 1
fi

# Extract node paths from the "Review Order" section
# Lines look like: "1. scripts/AGENTS.md (3 files)"
AFFECTED_NODES=()
while IFS= read -r line; do
    # Match lines like "1. path/AGENTS.md (N files)" or "1. CLAUDE.md (N files)"
    if [[ "$line" =~ ^[0-9]+\.\ (.+)\ \([0-9]+\ files?\) ]]; then
        AFFECTED_NODES+=("${BASH_REMATCH[1]}")
    fi
done <<< "$DETECT_OUTPUT"

# Also check for directly modified nodes
while IFS= read -r line; do
    if [[ "$line" =~ ^\*\ (.+\.(AGENTS|CLAUDE)\.md)$ ]] || [[ "$line" =~ ^\ \ \*\ (.+)$ ]]; then
        local_path="${BASH_REMATCH[1]}"
        # Only add if it's an AGENTS.md or CLAUDE.md and not already in the list
        if [[ "$local_path" =~ (AGENTS|CLAUDE)\.md$ ]]; then
            already=false
            for n in "${AFFECTED_NODES[@]:-}"; do
                [[ "$n" == "$local_path" ]] && already=true && break
            done
            $already || AFFECTED_NODES+=("$local_path")
        fi
    fi
done <<< "$DETECT_OUTPUT"

if [[ ${#AFFECTED_NODES[@]} -eq 0 ]]; then
    echo "No affected Intent Nodes found for $BASE_REF..$HEAD_REF."
    exit 2
fi

echo "# Intent Layer Update Suggestions"
echo ""
echo "Generated from diff: $BASE_REF..$HEAD_REF"
echo ""

# --- Dry-run mode ---
if $DRY_RUN || [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Dry-run mode: showing affected nodes only. Set ANTHROPIC_API_KEY for AI suggestions."
    echo ""
    echo "## Affected Nodes"
    echo ""
    for node in "${AFFECTED_NODES[@]}"; do
        echo "- $node"
    done
    exit 0
fi

# --- Helper: get the scope directory for a node ---
get_scope_dir() {
    local node="$1"
    local dir
    dir=$(dirname "$node")
    if [[ "$dir" == "." ]]; then
        echo ""
    else
        echo "$dir"
    fi
}

# --- Helper: filter sensitive files from diff ---
filter_sensitive_diff() {
    local diff_text="$1"
    # Remove diff hunks for sensitive files by checking each "diff --git" header
    # against the sensitive patterns list.
    # Uses here-string to avoid subshell from pipe (variable state must persist).
    local in_sensitive=false
    while IFS= read -r line; do
        if [[ "$line" == "diff --git"* ]]; then
            in_sensitive=false
            if echo "$line" | grep -qE "$SENSITIVE_PATTERNS"; then
                in_sensitive=true
            fi
        fi
        if ! $in_sensitive; then
            printf '%s\n' "$line"
        fi
    done <<< "$diff_text"
}

# --- Helper: call Haiku API with retries ---
call_haiku() {
    local node="$1"
    local diff_text="$2"
    local node_content="$3"

    local prompt
    prompt="Analyze this git diff against the current AGENTS.md content. Suggest specific additions or updates needed.

Current AGENTS.md ($node):
---
$node_content
---

Git diff for this area:
---
$diff_text
---

Return a JSON object with suggested updates. Each suggestion should specify which section it belongs to (Pitfalls, Contracts, Patterns, Context, Entry Points, or Code Map) and provide a title and body.

Rules:
- Only suggest things the diff actually changes or reveals. Don't invent issues.
- Keep suggestions concise (2-4 lines each).
- Focus on non-obvious gotchas, changed contracts, or new patterns.
- If nothing worth documenting, return empty suggestions array.

Return exactly this JSON format:
{\"suggestions\": [{\"section\": \"Pitfalls\", \"title\": \"...\", \"body\": \"...\"}]}"

    local request_body
    request_body=$(jq -n \
        --arg model "$MODEL" \
        --arg user_msg "$prompt" \
        '{
            model: $model,
            max_tokens: 1024,
            messages: [{role: "user", content: $user_msg}]
        }')

    local attempt=0
    local backoff=2
    local response=""

    while [[ $attempt -lt $MAX_RETRIES ]]; do
        attempt=$((attempt + 1))

        set +e
        response=$(curl -s --connect-timeout 10 --max-time 30 \
            -w "\n%{http_code}" \
            -H "x-api-key: ${ANTHROPIC_API_KEY}" \
            -H "anthropic-version: 2023-06-01" \
            -H "content-type: application/json" \
            "https://api.anthropic.com/v1/messages" \
            -d "$request_body" 2>/dev/null)
        local curl_exit=$?
        set -e

        if [[ $curl_exit -ne 0 ]]; then
            echo "Error: curl failed for $node (attempt $attempt/$MAX_RETRIES)" >&2
            sleep "$backoff"
            backoff=$((backoff * 2))
            continue
        fi

        # Split response body and HTTP status code
        local http_code
        http_code=$(echo "$response" | tail -1)
        local body
        body=$(echo "$response" | sed '$d')

        if [[ "$http_code" == "429" ]]; then
            echo "Rate limited for $node (attempt $attempt/$MAX_RETRIES), retrying in ${backoff}s..." >&2
            sleep "$backoff"
            backoff=$((backoff * 2))
            continue
        fi

        if [[ "$http_code" =~ ^2 ]]; then
            # Extract text content from API response
            local text_content
            text_content=$(echo "$body" | jq -r '.content[0].text // empty' 2>/dev/null)
            if [[ -n "$text_content" ]]; then
                echo "$text_content"
                return 0
            fi
        fi

        echo "Error: API returned HTTP $http_code for $node" >&2
        sleep "$backoff"
        backoff=$((backoff * 2))
    done

    echo "Error: All $MAX_RETRIES retries failed for $node" >&2
    return 1
}

# --- Process each affected node ---
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

RUNNING=0
for node in "${AFFECTED_NODES[@]}"; do
    # Get scoped diff
    scope_dir=$(get_scope_dir "$node")
    if [[ -n "$scope_dir" ]]; then
        raw_diff=$(git diff "$BASE_REF".."$HEAD_REF" -- "$scope_dir" 2>/dev/null || true)
    else
        raw_diff=$(git diff "$BASE_REF".."$HEAD_REF" 2>/dev/null || true)
    fi

    if [[ -z "$raw_diff" ]]; then
        continue
    fi

    # Filter sensitive files and truncate
    filtered_diff=$(filter_sensitive_diff "$raw_diff")
    truncated_diff=$(echo "$filtered_diff" | head -c "$MAX_DIFF_CHARS")

    # Read current AGENTS.md content
    if [[ ! -f "$node" ]]; then
        continue
    fi
    node_content=$(cat "$node")

    # Launch background job
    SAFE_NAME=$(echo "$node" | tr '/' '_')
    (
        result=$(call_haiku "$node" "$truncated_diff" "$node_content" 2>/dev/null) || true
        if [[ -n "$result" ]]; then
            echo "$result" > "$TEMP_DIR/$SAFE_NAME.json"
        fi
    ) &

    RUNNING=$((RUNNING + 1))
    if [[ $RUNNING -ge $MAX_PARALLEL ]]; then
        # wait -n requires bash 4.3+; fall back to polling job count
        if wait -n 2>/dev/null; then
            RUNNING=$((RUNNING - 1))
        else
            # Fallback: poll running jobs until one finishes
            while true; do
                CURRENT_JOBS=$(jobs -rp | wc -l | tr -d ' ')
                if [[ "$CURRENT_JOBS" -lt "$RUNNING" ]]; then
                    RUNNING="$CURRENT_JOBS"
                    break
                fi
                sleep 0.1
            done
        fi
    fi
done

# Wait for all background jobs
wait

# --- Format output ---
HAS_SUGGESTIONS=false

for node in "${AFFECTED_NODES[@]}"; do
    SAFE_NAME=$(echo "$node" | tr '/' '_')
    RESULT_FILE="$TEMP_DIR/$SAFE_NAME.json"

    if [[ ! -f "$RESULT_FILE" ]]; then
        continue
    fi

    raw_json=$(cat "$RESULT_FILE")

    # Try to parse as JSON. The response might have markdown fencing or extra text.
    # Strategy: strip fences, then try jq directly, then grep for a JSON object.
    clean_json=""

    # First try: raw text is valid JSON
    if echo "$raw_json" | jq -e '.suggestions' &>/dev/null; then
        clean_json="$raw_json"
    fi

    # Second try: strip markdown code fences
    if [[ -z "$clean_json" ]]; then
        stripped=$(echo "$raw_json" | sed '/^```/d' | tr -d '\n')
        if echo "$stripped" | jq -e '.suggestions' &>/dev/null; then
            clean_json="$stripped"
        fi
    fi

    # Third try: extract JSON from surrounding text by finding outermost braces
    if [[ -z "$clean_json" ]]; then
        extracted=$(echo "$raw_json" | tr -d '\n' | sed 's/.*\({.*"suggestions".*\)/\1/' | rev | sed 's/.*\(}.*\)/\1/' | rev || true)
        if [[ -n "$extracted" ]] && echo "$extracted" | jq -e '.suggestions' &>/dev/null; then
            clean_json="$extracted"
        fi
    fi

    if [[ -z "$clean_json" ]]; then
        continue
    fi

    suggestion_count=$(echo "$clean_json" | jq -r '.suggestions | length' 2>/dev/null || echo "0")

    if [[ -z "$suggestion_count" || "$suggestion_count" == "null" || "$suggestion_count" -eq 0 ]] 2>/dev/null; then
        continue
    fi

    HAS_SUGGESTIONS=true
    echo "## $node"
    echo ""

    for i in $(seq 0 $((suggestion_count - 1))); do
        section=$(echo "$clean_json" | jq -r ".suggestions[$i].section // \"Pitfalls\"" 2>/dev/null)
        title=$(echo "$clean_json" | jq -r ".suggestions[$i].title // \"\"" 2>/dev/null)
        body=$(echo "$clean_json" | jq -r ".suggestions[$i].body // \"\"" 2>/dev/null)

        if [[ -z "$title" || "$title" == "null" ]]; then
            continue
        fi

        echo "### Suggested addition to $section"
        echo ""
        echo "> **$title**"
        if [[ -n "$body" && "$body" != "null" ]]; then
            # Indent body lines with >
            echo "$body" | while IFS= read -r bline; do
                echo "> $bline"
            done
        fi
        echo ""
    done

    echo "---"
    echo ""
done

if ! $HAS_SUGGESTIONS; then
    echo "No suggestions generated. The changes may not require AGENTS.md updates."
    echo ""
fi

echo "Accept suggestions: Run \`integrate_pitfall.sh\` with the appropriate learning type."
