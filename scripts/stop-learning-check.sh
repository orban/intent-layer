#!/usr/bin/env bash
# Stop hook - Three-tier learning classifier with auto-capture
# Input: JSON on stdin with session_id, transcript_path, cwd, stop_hook_active, etc.
# Output: nothing (exit 0 = allow stop) or {"decision":"block","reason":"..."} via output_block
#
# Tier 1: Bash heuristic checks for signals (git diff, skeleton reports, injection log)
# Tier 2: Haiku API call with structured output as binary classifier
# Tier 3: Haiku extraction call → auto-write via learn.sh or queue via report_learning.sh
#
# Never blocks — writes summary to stderr instead. All paths exit 0.
# Everything fails open on error (API down, parse failure, missing tools).

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

# --- Tier 3: Extract and auto-write learnings ---

# Build extraction request — second Haiku call to pull structured learnings
EXTRACT_BODY=$(jq -n \
    --arg model "claude-haiku-4-5-20251001" \
    --arg system_prompt "You are extracting learnings from a coding session transcript for a codebase documentation system (Intent Layer).

Extract specific, actionable learnings. Each learning must be something an AI agent or developer would benefit from knowing next time they work in the same area.

Types:
- pitfall: Something that looks right but breaks, or looks wrong but is correct. Non-obvious gotchas.
- check: A verification step that should happen before a risky operation. \"Before X, verify Y.\"
- pattern: A multi-step process that isn't obvious from reading the code alone.
- insight: A design decision, constraint, or context that explains WHY something is the way it is.

Rules:
- Only extract genuine learnings (corrections, discoveries, workarounds, gotchas)
- Skip routine work (writing tests, committing, formatting)
- path must be relative to project root (e.g. \"src/api/\" or \"src/server/proxy.ts\")
- title must be under 50 characters
- detail should be 1-3 sentences, specific enough to act on
- confidence: \"high\" if clearly stated and actionable, \"medium\" if plausible but needs verification, \"low\" if ambiguous or inferred
- Return empty learnings array if nothing specific enough to extract
- Max 5 learnings per session" \
    --arg user_msg "$USER_MESSAGE" \
    '{
        model: $model,
        max_tokens: 1024,
        system: $system_prompt,
        messages: [{role: "user", content: $user_msg}],
        output_config: {
            format: {
                type: "json_schema",
                schema: {
                    type: "object",
                    properties: {
                        learnings: {
                            type: "array",
                            items: {
                                type: "object",
                                properties: {
                                    type: { type: "string", enum: ["pitfall", "check", "pattern", "insight"] },
                                    title: { type: "string" },
                                    detail: { type: "string" },
                                    path: { type: "string" },
                                    confidence: { type: "string", enum: ["high", "medium", "low"] }
                                },
                                required: ["type", "title", "detail", "path", "confidence"],
                                additionalProperties: false
                            }
                        }
                    },
                    required: ["learnings"],
                    additionalProperties: false
                }
            }
        }
    }')

set +e
EXTRACT_RESPONSE=$(curl -s --connect-timeout 5 --max-time 30 \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    "https://api.anthropic.com/v1/messages" \
    -d "$EXTRACT_BODY" 2>/dev/null)
EXTRACT_EXIT=$?
set -e

# Extraction failed — log to stderr and exit cleanly
if [[ $EXTRACT_EXIT -ne 0 || -z "$EXTRACT_RESPONSE" ]]; then
    echo "Intent Layer: learnings detected but extraction failed. Run /intent-layer:review to capture manually." >&2
    exit 0
fi

# Parse extracted learnings
LEARNINGS_JSON=$(echo "$EXTRACT_RESPONSE" | jq -r '.content[0].text' 2>/dev/null)
LEARNING_COUNT=$(echo "$LEARNINGS_JSON" | jq -r '.learnings | length' 2>/dev/null)

# No learnings extracted or parse failure — log to stderr and exit cleanly
if [[ -z "$LEARNING_COUNT" || "$LEARNING_COUNT" == "null" || "$LEARNING_COUNT" -eq 0 ]] 2>/dev/null; then
    echo "Intent Layer: learnings detected but none extracted. Run /intent-layer:review to capture manually." >&2
    exit 0
fi

# Dispatch each learning
AUTO_CAPTURED=0
QUEUED=0
CAPTURE_SUMMARY=""

for i in $(seq 0 $((LEARNING_COUNT - 1))); do
    L_TYPE=$(echo "$LEARNINGS_JSON" | jq -r ".learnings[$i].type" 2>/dev/null)
    L_TITLE=$(echo "$LEARNINGS_JSON" | jq -r ".learnings[$i].title" 2>/dev/null)
    L_DETAIL=$(echo "$LEARNINGS_JSON" | jq -r ".learnings[$i].detail" 2>/dev/null)
    L_PATH=$(echo "$LEARNINGS_JSON" | jq -r ".learnings[$i].path" 2>/dev/null)
    L_CONFIDENCE=$(echo "$LEARNINGS_JSON" | jq -r ".learnings[$i].confidence" 2>/dev/null)

    # Skip if any required field is empty
    if [[ -z "$L_TYPE" || -z "$L_TITLE" || -z "$L_DETAIL" || -z "$L_PATH" ]]; then
        continue
    fi

    # Normalize unrecognized confidence to medium
    case "$L_CONFIDENCE" in
        high|medium|low) ;;
        *) L_CONFIDENCE="medium" ;;
    esac

    if [[ "$L_CONFIDENCE" == "high" ]]; then
        # Direct-write via learn.sh (has dedup gate)
        set +e
        "$PLUGIN_ROOT/scripts/learn.sh" \
            --project "$PROJECT_ROOT" \
            --path "$L_PATH" \
            --type "$L_TYPE" \
            --title "$L_TITLE" \
            --detail "$L_DETAIL" 2>/dev/null
        LEARN_EXIT=$?
        set -e

        if [[ $LEARN_EXIT -eq 0 ]]; then
            AUTO_CAPTURED=$((AUTO_CAPTURED + 1))
            CAPTURE_SUMMARY+="  ✓ [$L_TYPE] $L_TITLE"$'\n'
        elif [[ $LEARN_EXIT -eq 2 ]]; then
            # Duplicate — already known, skip silently
            CAPTURE_SUMMARY+="  = [$L_TYPE] $L_TITLE (already documented)"$'\n'
        else
            # learn.sh failed (no covering node, etc.) — queue with confidence
            set +e
            "$PLUGIN_ROOT/scripts/report_learning.sh" \
                --project "$PROJECT_ROOT" \
                --path "$L_PATH" \
                --type "$L_TYPE" \
                --title "$L_TITLE" \
                --detail "$L_DETAIL" \
                --confidence "$L_CONFIDENCE" 2>/dev/null
            set -e
            QUEUED=$((QUEUED + 1))
            CAPTURE_SUMMARY+="  ? [$L_TYPE] $L_TITLE (queued — no covering node)"$'\n'
        fi
    else
        # Medium/low confidence — queue for human triage
        set +e
        "$PLUGIN_ROOT/scripts/report_learning.sh" \
            --project "$PROJECT_ROOT" \
            --path "$L_PATH" \
            --type "$L_TYPE" \
            --title "$L_TITLE" \
            --detail "$L_DETAIL" \
            --confidence "$L_CONFIDENCE" 2>/dev/null
        set -e
        QUEUED=$((QUEUED + 1))
        CAPTURE_SUMMARY+="  ? [$L_TYPE] $L_TITLE (queued — $L_CONFIDENCE confidence)"$'\n'
    fi
done

# Stderr summary — never block
if [[ $AUTO_CAPTURED -gt 0 || $QUEUED -gt 0 ]]; then
    echo "Intent Layer: captured $((AUTO_CAPTURED + QUEUED)) learning(s) ($AUTO_CAPTURED auto-integrated, $QUEUED queued for review)" >&2
    if [[ -n "$CAPTURE_SUMMARY" ]]; then
        echo "$CAPTURE_SUMMARY" >&2
    fi
    if [[ $QUEUED -gt 0 ]]; then
        echo "Run /intent-layer:review to triage." >&2
    fi
fi
exit 0
