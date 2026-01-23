#!/usr/bin/env bash
# SessionStart hook - Injects recent learnings into agent context
# Input: JSON on stdin with session info
# Output: JSON with additionalContext to stdout

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")}"
source "$PLUGIN_ROOT/lib/common.sh"

AGGREGATE_SCRIPT="$PLUGIN_ROOT/lib/aggregate_learnings.sh"

if [[ ! -f "$AGGREGATE_SCRIPT" ]]; then
    exit 0
fi

LEARNINGS=$("$AGGREGATE_SCRIPT" --days 7 --format summary 2>/dev/null || true)

if [[ -z "$LEARNINGS" ]]; then
    exit 0
fi

# Build the context message
CONTEXT="## Intent Layer: Recent Learnings

The following mistakes were recently captured and converted to Intent Layer updates.
Be aware of these patterns when working in related areas.

$LEARNINGS"

# Output as JSON with additionalContext
output_context "SessionStart" "$CONTEXT"
