#!/usr/bin/env bash
# Stop hook - Two-tier learning classifier
# Input: JSON on stdin with session_id, transcript_path, cwd, stop_hook_active, etc.
# Output: nothing (exit 0 = allow stop) or {"decision":"block","reason":"..."} via output_block
#
# Tier 1: Bash heuristic checks for signals (git diff, skeleton reports, injection log)
# Tier 2: Haiku API call with structured output as binary classifier
# Only blocks when Haiku explicitly says should_capture: true. Everything else fails open.

set -euo pipefail

# Source shared library
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
source "$PLUGIN_ROOT/lib/common.sh"

# --- Guards ---

# jq is required for stdin parsing and API response handling
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat) || true
if [[ -z "$INPUT" ]]; then
    exit 0
fi

# Re-entry guard: prevent infinite loops when main model is already
# continuing from a previous stop hook block
STOP_ACTIVE=$(json_get "$INPUT" '.stop_hook_active' 'false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

# Project root
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"

# No Intent Layer = nothing to capture
if [[ ! -d "$PROJECT_ROOT/.intent-layer" ]]; then
    exit 0
fi

# --- Tier 1: Heuristic signal detection ---

SIGNALS=""

# Check 1: Uncommitted changes to AGENTS.md or CLAUDE.md files
if command -v git &>/dev/null && git -C "$PROJECT_ROOT" rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    if git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -qE '(AGENTS|CLAUDE)\.md$'; then
        CHANGED_FILES=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -E '(AGENTS|CLAUDE)\.md$' | head -5)
        SIGNALS+="- Uncommitted changes to: $CHANGED_FILES"$'\n'
    fi
fi

# Check 2: Skeleton reports in pending
PENDING_DIR="$PROJECT_ROOT/.intent-layer/mistakes/pending"
if [[ -d "$PENDING_DIR" ]]; then
    SKELETON_COUNT=$(find "$PENDING_DIR" -name 'SKELETON-*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$SKELETON_COUNT" -gt 0 ]]; then
        SIGNALS+="- $SKELETON_COUNT skeleton report(s) in pending/"$'\n'
    fi

    FAILURE_COUNT=$(find "$PENDING_DIR" -name 'FAILURE-*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$FAILURE_COUNT" -gt 0 ]]; then
        SIGNALS+="- $FAILURE_COUNT tool failure report(s) in pending/"$'\n'
    fi
fi

# Check 3: Injection log exists and is non-empty
INJECTION_LOG="$PROJECT_ROOT/.intent-layer/hooks/injections.log"
if [[ -s "$INJECTION_LOG" ]]; then
    LOG_LINES=$(wc -l < "$INJECTION_LOG" | tr -d ' ')
    SIGNALS+="- Injection log has $LOG_LINES entries"$'\n'
fi

# No signals = nothing worth evaluating
if [[ -z "$SIGNALS" ]]; then
    exit 0
fi

# --- Tier 2: Haiku binary classifier ---

# Tier 2 requires both curl and an API key. Without either, fail open.
if ! command -v curl &>/dev/null || [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    exit 0
fi

# Read transcript for context
TRANSCRIPT_PATH=$(json_get "$INPUT" '.transcript_path' '')
TRANSCRIPT_EXCERPT=""
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
    TRANSCRIPT_EXCERPT=$(tail -200 "$TRANSCRIPT_PATH" | head -c 50000 || true)
fi

# If no transcript available, we can't classify meaningfully — fail open
if [[ -z "$TRANSCRIPT_EXCERPT" ]]; then
    exit 0
fi

# Build the user message with signal summary + transcript
USER_MESSAGE="Tier 1 signals detected:
${SIGNALS}
Session transcript (last ~200 lines):
${TRANSCRIPT_EXCERPT}"

# Build API request body
REQUEST_BODY=$(jq -n \
    --arg model "claude-haiku-4-5-20251001" \
    --arg system_prompt "You are a learning classifier for a codebase documentation system. Given a session transcript excerpt and detected signals, determine if the session contains discoveries worth documenting.

Examples of should_capture: true:
- User corrected agent's assumption about config format
- Agent discovered rate limiting silently drops requests
- A non-obvious gotcha was found during debugging
- A workaround was needed for an undocumented limitation

Examples of should_capture: false:
- Normal coding session, agent wrote tests and fixed a typo
- Agent edited AGENTS.md as part of routine /intent-layer-maintenance
- Simple Q&A session with no unexpected discoveries
- User asked agent to push, commit, or do routine git operations

Return should_capture: true only for genuine documentation gaps." \
    --arg user_msg "$USER_MESSAGE" \
    '{
        model: $model,
        max_tokens: 128,
        system: $system_prompt,
        messages: [{role: "user", content: $user_msg}],
        output_config: {
            format: {
                type: "json_schema",
                schema: {
                    type: "object",
                    properties: {
                        should_capture: {type: "boolean"}
                    },
                    required: ["should_capture"],
                    additionalProperties: false
                }
            }
        }
    }')

# Call Haiku API — wrap in set +e to prevent set -e from killing script on failure
set +e
RESPONSE=$(curl -s --connect-timeout 5 --max-time 20 \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    "https://api.anthropic.com/v1/messages" \
    -d "$REQUEST_BODY" 2>/dev/null)
CURL_EXIT=$?
set -e

# curl failed — fail open
if [[ $CURL_EXIT -ne 0 || -z "$RESPONSE" ]]; then
    exit 0
fi

# Extract the classification from the response
# Response shape: {"content":[{"type":"text","text":"{\"should_capture\":true}"}],...}
SHOULD_CAPTURE=$(echo "$RESPONSE" | jq -r '.content[0].text' 2>/dev/null | jq -r '.should_capture' 2>/dev/null)

# If we can't parse the response, fail open
if [[ "$SHOULD_CAPTURE" != "true" ]]; then
    exit 0
fi

# Haiku says capture — block with reason
output_block "Session contains learnings worth capturing. Run /intent-layer-compound to document them."
