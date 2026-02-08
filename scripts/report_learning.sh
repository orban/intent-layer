#!/usr/bin/env bash
set -euo pipefail

# report_learning.sh - Swarm-friendly learning capture (non-interactive)
#
# Usage: report_learning.sh --project <path> --path <file> --type <type> --title <text> --detail <text> [--agent-id <id>]
#
# Designed for agent swarm workers. All arguments required (no prompts).
# Returns the path to the created report on stdout.
#
# Required:
#   --project PATH    Project root directory
#   --path FILE       File or directory the learning relates to
#   --type TYPE       Learning type: pitfall, check, pattern, insight
#   --title TEXT      Short title (50 chars max)
#   --detail TEXT     Full description of the learning
#
# Optional:
#   --agent-id ID     Identifier for the reporting agent
#   -h, --help        Show this help
#
# Examples:
#   report_learning.sh --project /repo --path src/api/ --type pitfall \
#     --title "Arrow functions in API" --detail "Handlers use arrow syntax"
#
#   report_learning.sh --project /repo --path src/db/migrate.ts --type check \
#     --title "Verify backup before migration" --detail "Lost data when migration failed" \
#     --agent-id "worker-3"

show_help() {
    sed -n '3,/^$/p' "$0" | sed 's/^# //' | sed 's/^#//'
    exit 0
}

PROJECT=""
FILE_PATH=""
LEARNING_TYPE=""
TITLE=""
DETAIL=""
AGENT_ID=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --project) PROJECT="$2"; shift 2 ;;
        --path) FILE_PATH="$2"; shift 2 ;;
        --type) LEARNING_TYPE="$2"; shift 2 ;;
        --title) TITLE="$2"; shift 2 ;;
        --detail) DETAIL="$2"; shift 2 ;;
        --agent-id) AGENT_ID="$2"; shift 2 ;;
        *) echo "Error: Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Validate required args
MISSING=""
[[ -z "$PROJECT" ]] && MISSING="$MISSING --project"
[[ -z "$FILE_PATH" ]] && MISSING="$MISSING --path"
[[ -z "$LEARNING_TYPE" ]] && MISSING="$MISSING --type"
[[ -z "$TITLE" ]] && MISSING="$MISSING --title"
[[ -z "$DETAIL" ]] && MISSING="$MISSING --detail"

if [[ -n "$MISSING" ]]; then
    echo "Error: Missing required arguments:$MISSING" >&2
    echo "Usage: report_learning.sh --project <path> --path <file> --type <type> --title <text> --detail <text>" >&2
    exit 1
fi

# Validate type
case "$LEARNING_TYPE" in
    pitfall|check|pattern|insight) ;;
    *) echo "Error: Invalid type '$LEARNING_TYPE'. Must be: pitfall, check, pattern, insight" >&2; exit 1 ;;
esac

# Resolve file path to directory
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="$PROJECT/$FILE_PATH"
fi
if [[ -f "$FILE_PATH" ]]; then
    DIR_PATH=$(dirname "$FILE_PATH")
elif [[ -d "$FILE_PATH" ]]; then
    DIR_PATH="$FILE_PATH"
else
    DIR_PATH=$(dirname "$FILE_PATH")
fi

# Delegate to capture_mistake.sh
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
CAPTURE_SCRIPT="$PLUGIN_ROOT/scripts/capture_mistake.sh"

# Build args
CAPTURE_ARGS=(
    --non-interactive
    --type "$LEARNING_TYPE"
    --dir "$DIR_PATH"
    --operation "$TITLE"
    --what "$DETAIL"
    --cause "$DETAIL"
)

[[ -n "$AGENT_ID" ]] && CAPTURE_ARGS+=(--agent-id "$AGENT_ID")

# Set project dir for capture script
export CLAUDE_PROJECT_DIR="$PROJECT"

cd "$PROJECT"
"$CAPTURE_SCRIPT" "${CAPTURE_ARGS[@]}"
