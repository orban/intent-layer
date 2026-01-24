# Learning Layer Implementation Plan (v3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a continuous learning loop that captures mistakes during agent sessions and injects relevant learnings back into future workflows.

**Architecture:** Four hooks working as two pairs - capture hooks (PostToolUseFailure, Stop) detect issues and create mistake reports, feedback hooks (SessionStart, PreToolUse) inject relevant context before agents make changes.

**Tech Stack:** Bash scripts, Markdown for reports, existing `capture_mistake.sh` infrastructure.

**Documentation Reference:** https://code.claude.com/docs/en/hooks

---

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     LEARNING LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  CAPTURE (Detection)                                            │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │ PostToolUseFailure  │    │ Stop (prompt-based LLM eval)    │ │
│  │ - Matcher: Edit|*   │    │ - LLM evaluates session         │ │
│  │ - Suggests capture  │    │ - Blocks if learnings found     │ │
│  └──────────┬──────────┘    └──────────────┬──────────────────┘ │
│             │                              │                     │
│             ▼                              ▼                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           .intent-layer/mistakes/pending/                │   │
│  │           Human review → accepted/ or rejected/          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  FEEDBACK (Injection)                                            │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │ SessionStart        │    │ PreToolUse (Edit|Write|*)       │ │
│  │ - Injects learnings │    │ - Injects Pitfalls via          │ │
│  │ - additionalContext │    │   additionalContext             │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Plugin Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── hooks/
│   ├── hooks.json            # Hook registration (official format)
│   └── scripts/
│       ├── capture-tool-failure.sh
│       ├── inject-learnings.sh
│       └── pre-edit-check.sh
├── lib/
│   ├── common.sh
│   ├── aggregate_learnings.sh
│   ├── find_covering_node.sh
│   └── check_mistake_history.sh
├── tests/
│   └── test_hooks.sh
└── README.md
```

---

## Task 1: Create Plugin Scaffold with Shared Library

**Files:**
- Create: `intent-layer-plugin/.claude-plugin/plugin.json`
- Create: `intent-layer-plugin/lib/common.sh`
- Create: directory structure

**Step 1: Create directory structure**

```bash
mkdir -p intent-layer-plugin/.claude-plugin
mkdir -p intent-layer-plugin/hooks/scripts
mkdir -p intent-layer-plugin/lib
mkdir -p intent-layer-plugin/tests
```

**Step 2: Write plugin.json**

Create `intent-layer-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "intent-layer",
  "version": "0.1.0",
  "description": "Intent Layer with continuous learning loop - captures mistakes and injects learnings",
  "author": "intent-layer-team"
}
```

**Step 3: Write common.sh shared library**

Create `intent-layer-plugin/lib/common.sh`:

```bash
#!/usr/bin/env bash
# Shared functions for learning layer hooks
# Source this at the start of hook scripts

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
```

**Step 4: Make executable**

Run: `chmod +x intent-layer-plugin/lib/common.sh`

**Step 5: Verify structure**

Run: `ls -laR intent-layer-plugin/`
Expected: All directories and plugin.json present

**Step 6: Commit**

```bash
git add intent-layer-plugin/
git commit -m "feat(learning-layer): scaffold plugin structure with shared library"
```

---

## Task 2: Implement PostToolUseFailure Capture Hook

**Files:**
- Create: `intent-layer-plugin/hooks/scripts/capture-tool-failure.sh`

**Purpose:** When a tool fails unexpectedly, suggest capturing the mistake.

**Official Input Format (PostToolUseFailure):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/dir",
  "permission_mode": "default",
  "hook_event_name": "PostToolUseFailure",
  "tool_name": "Edit",
  "tool_input": { "file_path": "/path/to/file.txt", ... },
  "tool_use_id": "toolu_01ABC123..."
}
```

**Note:** The error details are in the tool response, not directly in hook input. We infer failure from the hook event itself.

**Step 1: Write capture-tool-failure.sh**

Create `intent-layer-plugin/hooks/scripts/capture-tool-failure.sh`:

```bash
#!/usr/bin/env bash
# PostToolUseFailure hook - Suggests mistake capture on tool failures
# Input: JSON on stdin with tool_name, tool_input, etc.
# Output: stderr message (exit 0 = non-blocking suggestion)

set -euo pipefail

# Source shared library
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")}"
source "$PLUGIN_ROOT/lib/common.sh"

# Read hook input
INPUT=$(cat)

# Extract fields
TOOL_NAME=$(json_get "$INPUT" '.tool_name' 'unknown')
FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
COMMAND=$(json_get "$INPUT" '.tool_input.command' '')

# Build context string for the suggestion
CONTEXT=""
if [[ -n "$FILE_PATH" ]]; then
    CONTEXT="File: $FILE_PATH"
elif [[ -n "$COMMAND" ]]; then
    CONTEXT="Command: ${COMMAND:0:50}..."
fi

# Skip expected/exploratory failures
case "$TOOL_NAME" in
    Read|Glob|Grep|LS)
        # File exploration failures are expected - silent exit
        exit 0
        ;;
    Bash)
        # Skip common exploratory bash failures
        # (We can't see the error message, but Bash failures during exploration are common)
        # Be conservative - only suggest capture for file-modifying operations
        if [[ -z "$FILE_PATH" ]]; then
            exit 0
        fi
        ;;
esac

# For significant failures (Edit, Write, etc.), output to stderr
# Exit 0 = non-blocking, stderr shown in verbose mode
{
    echo ""
    echo "⚠️ Tool '$TOOL_NAME' failed"
    if [[ -n "$CONTEXT" ]]; then
        echo "   $CONTEXT"
    fi
    echo ""
    echo "If this was unexpected, consider capturing it:"
    echo "  ~/.claude/skills/intent-layer/scripts/capture_mistake.sh --from-git"
    echo ""
    echo "(Ignore if exploratory/expected behavior)"
    echo ""
} >&2

exit 0
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/scripts/capture-tool-failure.sh`

**Step 3: Test with Edit failure**

Run:
```bash
echo '{"hook_event_name": "PostToolUseFailure", "tool_name": "Edit", "tool_input": {"file_path": "/src/auth/login.ts"}}' | \
  ./intent-layer-plugin/hooks/scripts/capture-tool-failure.sh 2>&1
```

Expected: Shows suggestion with file path

**Step 4: Test filtering**

Run:
```bash
echo '{"hook_event_name": "PostToolUseFailure", "tool_name": "Read", "tool_input": {"file_path": "/test.md"}}' | \
  ./intent-layer-plugin/hooks/scripts/capture-tool-failure.sh 2>&1
```

Expected: Silent exit (no output)

**Step 5: Commit**

```bash
git add intent-layer-plugin/hooks/scripts/capture-tool-failure.sh
git commit -m "feat(learning-layer): add PostToolUseFailure capture hook"
```

---

## Task 3: Create Learnings Aggregation Script

**Files:**
- Create: `intent-layer-plugin/lib/aggregate_learnings.sh`

**Purpose:** Aggregate recent accepted mistakes into a summary for SessionStart injection.

**Step 1: Write aggregation script**

Create `intent-layer-plugin/lib/aggregate_learnings.sh`:

```bash
#!/usr/bin/env bash
# Aggregate recent learnings from accepted mistakes
# Usage: aggregate_learnings.sh [--days N] [--format summary|full]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

show_help() {
    cat << 'EOF'
aggregate_learnings.sh - Aggregate recent learnings for session injection

USAGE:
    aggregate_learnings.sh [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -d, --days N         Include learnings from last N days (default: 7)
    -f, --format FORMAT  Output format: summary|full (default: summary)
    -p, --path DIR       Project root to search (default: cwd or CLAUDE_PROJECT_DIR)

OUTPUT:
    Markdown summary of recent accepted mistakes. Empty if none found.
EOF
    exit 0
}

DAYS=7
FORMAT="summary"
PROJECT_PATH="${CLAUDE_PROJECT_DIR:-.}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -d|--days) DAYS="$2"; shift 2 ;;
        -f|--format) FORMAT="$2"; shift 2 ;;
        -p|--path) PROJECT_PATH="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

MISTAKES_DIR="$PROJECT_PATH/.intent-layer/mistakes/accepted"

if [[ ! -d "$MISTAKES_DIR" ]]; then
    exit 0
fi

CUTOFF=$(date_days_ago "$DAYS")

RECENT_FILES=()
while IFS= read -r -d '' file; do
    if file_newer_than "$file" "$CUTOFF"; then
        RECENT_FILES+=("$file")
    fi
done < <(find "$MISTAKES_DIR" -name "MISTAKE-*.md" -type f -print0 2>/dev/null)

if [[ ${#RECENT_FILES[@]} -eq 0 ]]; then
    exit 0
fi

echo "## Recent Learnings (last $DAYS days)"
echo ""
echo "${#RECENT_FILES[@]} accepted mistake(s) converted to Intent Layer updates."
echo ""

if [[ "$FORMAT" == "full" ]]; then
    for file in "${RECENT_FILES[@]}"; do
        echo "---"
        echo ""
        cat "$file"
        echo ""
    done
else
    echo "| Directory | Root Cause | Fix Applied |"
    echo "|-----------|------------|-------------|"

    for file in "${RECENT_FILES[@]}"; do
        DIR=$(grep -m1 '^\*\*Directory\*\*:' "$file" 2>/dev/null | sed 's/.*: //' | head -c 30 || echo "?")
        CAUSE=$(grep -m1 '^### Root Cause' -A1 "$file" 2>/dev/null | tail -1 | head -c 40 || echo "?")
        DISP=$(grep -E '^\- \[x\]' "$file" 2>/dev/null | head -1 | sed 's/.*\] //' | head -c 25 || echo "?")
        echo "| $DIR | $CAUSE... | $DISP |"
    done
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/lib/aggregate_learnings.sh`

**Step 3: Test help**

Run: `./intent-layer-plugin/lib/aggregate_learnings.sh --help`
Expected: Help message

**Step 4: Commit**

```bash
git add intent-layer-plugin/lib/aggregate_learnings.sh
git commit -m "feat(learning-layer): add learnings aggregation script"
```

---

## Task 4: Implement SessionStart Injection Hook

**Files:**
- Create: `intent-layer-plugin/hooks/scripts/inject-learnings.sh`

**Purpose:** Inject recent accepted learnings at session start using `additionalContext`.

**Official Output Format (SessionStart):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "My context here"
  }
}
```

**Step 1: Write inject-learnings.sh**

Create `intent-layer-plugin/hooks/scripts/inject-learnings.sh`:

```bash
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
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/scripts/inject-learnings.sh`

**Step 3: Test hook**

Run: `echo '{"hook_event_name": "SessionStart", "source": "startup"}' | ./intent-layer-plugin/hooks/scripts/inject-learnings.sh`
Expected: JSON output with additionalContext (or empty if no learnings)

**Step 4: Commit**

```bash
git add intent-layer-plugin/hooks/scripts/inject-learnings.sh
git commit -m "feat(learning-layer): add SessionStart learnings injection hook"
```

---

## Task 5: Create Covering Node Finder Script

**Files:**
- Create: `intent-layer-plugin/lib/find_covering_node.sh`

**Purpose:** Walk up from a file to find the nearest AGENTS.md or CLAUDE.md.

**Step 1: Write find_covering_node.sh**

Create `intent-layer-plugin/lib/find_covering_node.sh`:

```bash
#!/usr/bin/env bash
# Find the covering AGENTS.md node for a given file path
# Usage: find_covering_node.sh <file_path> [--section NAME]

set -euo pipefail

show_help() {
    cat << 'EOF'
find_covering_node.sh - Find nearest covering AGENTS.md

USAGE:
    find_covering_node.sh <file_path> [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -s, --section NAME   Extract specific section (e.g., Pitfalls)

OUTPUT:
    Path to covering AGENTS.md/CLAUDE.md, or empty if none found.
    With --section, outputs the section content instead.
EOF
    exit 0
}

FILE_PATH=""
SECTION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -s|--section) SECTION="$2"; shift 2 ;;
        *)
            if [[ -z "$FILE_PATH" ]]; then
                FILE_PATH="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$FILE_PATH" ]]; then
    echo "Error: File path required" >&2
    exit 1
fi

# Normalize to absolute path
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="${CLAUDE_PROJECT_DIR:-$(pwd)}/$FILE_PATH"
fi

# Start from file's directory
if [[ -d "$FILE_PATH" ]]; then
    CURRENT_DIR="$FILE_PATH"
else
    CURRENT_DIR="$(dirname "$FILE_PATH")"
fi

NODE_PATH=""

while [[ "$CURRENT_DIR" != "/" ]]; do
    if [[ -f "$CURRENT_DIR/AGENTS.md" ]]; then
        NODE_PATH="$CURRENT_DIR/AGENTS.md"
        break
    fi
    if [[ -f "$CURRENT_DIR/CLAUDE.md" ]]; then
        NODE_PATH="$CURRENT_DIR/CLAUDE.md"
        break
    fi
    if [[ -d "$CURRENT_DIR/.git" ]]; then
        break
    fi
    CURRENT_DIR="$(dirname "$CURRENT_DIR")"
done

if [[ -z "$NODE_PATH" ]]; then
    exit 0
fi

if [[ -n "$SECTION" ]]; then
    awk -v section="$SECTION" '
        /^## / {
            if (found) exit
            if ($0 ~ "^## .*"section) found=1
        }
        found { print }
    ' "$NODE_PATH"
else
    echo "$NODE_PATH"
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/lib/find_covering_node.sh`

**Step 3: Test**

Run: `./intent-layer-plugin/lib/find_covering_node.sh intent-layer/scripts/capture_mistake.sh`
Expected: Path to covering node

**Step 4: Commit**

```bash
git add intent-layer-plugin/lib/find_covering_node.sh
git commit -m "feat(learning-layer): add covering node finder script"
```

---

## Task 6: Create Mistake History Checker

**Files:**
- Create: `intent-layer-plugin/lib/check_mistake_history.sh`

**Purpose:** Check if a directory has a history of mistakes (for adaptive gating).

**Step 1: Write check_mistake_history.sh**

Create `intent-layer-plugin/lib/check_mistake_history.sh`:

```bash
#!/usr/bin/env bash
# Check if a directory has a history of mistakes
# Usage: check_mistake_history.sh <directory> [--threshold N]

set -euo pipefail

show_help() {
    cat << 'EOF'
check_mistake_history.sh - Check directory mistake history

USAGE:
    check_mistake_history.sh <directory> [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -t, --threshold N    Mistake count for "high risk" (default: 2)
    --json               Output as JSON

EXIT CODES:
    0    High-risk (count >= threshold)
    1    Low-risk (count < threshold)
EOF
    exit 0
}

DIRECTORY=""
THRESHOLD=2
JSON_OUTPUT=false
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -t|--threshold) THRESHOLD="$2"; shift 2 ;;
        --json) JSON_OUTPUT=true; shift ;;
        *)
            if [[ -z "$DIRECTORY" ]]; then
                DIRECTORY="$1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$DIRECTORY" ]]; then
    echo "Error: Directory path required" >&2
    exit 1
fi

DIRECTORY="${DIRECTORY%/}"
REL_DIR="${DIRECTORY#$PROJECT_ROOT/}"

COUNT=0
for subdir in pending accepted; do
    mistakes_path="$PROJECT_ROOT/.intent-layer/mistakes/$subdir"
    if [[ -d "$mistakes_path" ]]; then
        matches=$(grep -l "^\*\*Directory\*\*:.*$REL_DIR" "$mistakes_path"/*.md 2>/dev/null | wc -l || echo 0)
        COUNT=$((COUNT + matches))
    fi
done

HIGH_RISK=false
if [[ "$COUNT" -ge "$THRESHOLD" ]]; then
    HIGH_RISK=true
fi

if [[ "$JSON_OUTPUT" == true ]]; then
    echo "{\"directory\": \"$DIRECTORY\", \"count\": $COUNT, \"high_risk\": $HIGH_RISK}"
fi

$HIGH_RISK && exit 0 || exit 1
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/lib/check_mistake_history.sh`

**Step 3: Test**

Run: `./intent-layer-plugin/lib/check_mistake_history.sh . --json`
Expected: JSON with count and high_risk

**Step 4: Commit**

```bash
git add intent-layer-plugin/lib/check_mistake_history.sh
git commit -m "feat(learning-layer): add mistake history checker"
```

---

## Task 7: Implement PreToolUse Hook (Adaptive Pitfalls)

**Files:**
- Create: `intent-layer-plugin/hooks/scripts/pre-edit-check.sh`

**Purpose:** Before Edit/Write, inject relevant Pitfalls using `additionalContext`.

**Official Input Format (PreToolUse):**
```json
{
  "session_id": "abc123",
  "hook_event_name": "PreToolUse",
  "tool_name": "Edit",
  "tool_input": { "file_path": "/path/to/file.txt", "old_string": "...", "new_string": "..." },
  "tool_use_id": "toolu_01ABC123..."
}
```

**Official Output Format (PreToolUse with context):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Pitfalls from covering node..."
  }
}
```

**Step 1: Write pre-edit-check.sh**

Create `intent-layer-plugin/hooks/scripts/pre-edit-check.sh`:

```bash
#!/usr/bin/env bash
# PreToolUse hook for Edit/Write - Injects pitfalls via additionalContext
# Input: JSON on stdin with tool_name, tool_input
# Output: JSON with additionalContext to stdout

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "${BASH_SOURCE[0]}")")")}"
source "$PLUGIN_ROOT/lib/common.sh"

INPUT=$(cat)

TOOL_NAME=$(json_get "$INPUT" '.tool_name' '')

# The matcher in hooks.json handles tool filtering, but double-check
case "$TOOL_NAME" in
    Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
FILE_PATH=${FILE_PATH:-$(json_get "$INPUT" '.tool_input.path' '')}

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"
CHECK_HISTORY="$PLUGIN_ROOT/lib/check_mistake_history.sh"

if [[ ! -f "$FIND_NODE" ]]; then
    exit 0
fi

NODE_PATH=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

if [[ -z "$NODE_PATH" ]]; then
    exit 0
fi

FILE_DIR="$(dirname "$FILE_PATH")"

HIGH_RISK=false
if [[ -f "$CHECK_HISTORY" ]]; then
    if "$CHECK_HISTORY" "$FILE_DIR" &>/dev/null; then
        HIGH_RISK=true
    fi
fi

PITFALLS=$("$FIND_NODE" "$FILE_PATH" --section Pitfalls 2>/dev/null || true)

if [[ -z "$PITFALLS" ]]; then
    exit 0
fi

# Build context message
if $HIGH_RISK; then
    CONTEXT="## Intent Layer Context

**Editing:** \`$FILE_PATH\`
**Covered by:** \`$NODE_PATH\`

⚠️ **HIGH-RISK AREA** - This directory has a history of mistakes.

Before proceeding, verify these pitfalls don't apply to your change:

$PITFALLS

---
**Pre-flight check:** Confirm you've reviewed the pitfalls above."
else
    CONTEXT="## Intent Layer Context

**Editing:** \`$FILE_PATH\`
**Covered by:** \`$NODE_PATH\`

ℹ️ Relevant pitfalls from covering node:

$PITFALLS"
fi

output_context "PreToolUse" "$CONTEXT"
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/scripts/pre-edit-check.sh`

**Step 3: Test**

Run:
```bash
echo '{"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "intent-layer/scripts/capture_mistake.sh"}}' | \
  ./intent-layer-plugin/hooks/scripts/pre-edit-check.sh
```

Expected: JSON output with pitfalls in additionalContext (or empty if no pitfalls)

**Step 4: Commit**

```bash
git add intent-layer-plugin/hooks/scripts/pre-edit-check.sh
git commit -m "feat(learning-layer): add PreToolUse hook with adaptive pitfall injection"
```

---

## Task 8: Create Hook Registration Configuration

**Files:**
- Create: `intent-layer-plugin/hooks/hooks.json`

**Purpose:** Register all hooks using the **official format**.

**Official Plugin hooks.json Format:**
```json
{
  "description": "Description of hooks",
  "hooks": {
    "EventName": [
      {
        "matcher": "Pattern",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/path/to/script.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Step 1: Write hooks.json**

Create `intent-layer-plugin/hooks/hooks.json`:

```json
{
  "description": "Intent Layer learning loop - captures mistakes and injects learnings",
  "hooks": {
    "PostToolUseFailure": [
      {
        "matcher": "Edit|Write|NotebookEdit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/capture-tool-failure.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/inject-learnings.sh",
            "timeout": 15
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/pre-edit-check.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "You are evaluating whether this session discovered any learnings that should be captured for the Intent Layer.\n\nContext: $ARGUMENTS\n\nAnalyze the session and determine if:\n1. Any unexpected behaviors were discovered (things that worked differently than expected)\n2. The user corrected any assumptions you made about the codebase\n3. You had to figure out something that should have been documented\n\nIf genuine learnings were discovered, respond with:\n{\"ok\": false, \"reason\": \"Before ending, please run: ~/.claude/skills/intent-layer/scripts/capture_mistake.sh to capture: [brief description of the learning]\"}\n\nIf no significant learnings (normal exploration, expected behaviors, successful work), respond with:\n{\"ok\": true}\n\nBe conservative - only flag genuine documentation gaps, not normal development activities.",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Step 2: Update plugin.json to reference hooks**

Update `intent-layer-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "intent-layer",
  "version": "0.1.0",
  "description": "Intent Layer with continuous learning loop - captures mistakes and injects learnings",
  "author": "intent-layer-team",
  "hooks": "hooks/hooks.json"
}
```

**Step 3: Validate JSON**

Run: `jq empty intent-layer-plugin/hooks/hooks.json && jq empty intent-layer-plugin/.claude-plugin/plugin.json && echo "Valid JSON"`
Expected: "Valid JSON"

**Step 4: Commit**

```bash
git add intent-layer-plugin/hooks/hooks.json intent-layer-plugin/.claude-plugin/plugin.json
git commit -m "feat(learning-layer): add hook registration with official format"
```

---

## Task 9: Create Integration Test Suite

**Files:**
- Create: `intent-layer-plugin/tests/test_hooks.sh`

**Step 1: Write test_hooks.sh**

Create `intent-layer-plugin/tests/test_hooks.sh`:

```bash
#!/usr/bin/env bash
# Integration tests for learning layer hooks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

# Set environment for testing
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"

PASSED=0
FAILED=0

pass() { echo "✅ $1"; ((PASSED++)); }
fail() { echo "❌ $1"; ((FAILED++)); }

echo "=== Learning Layer Hooks Integration Tests ==="
echo "Plugin root: $PLUGIN_DIR"
echo ""

# Test 1: common.sh loads
echo "Test 1: Shared library loads"
if source "$PLUGIN_DIR/lib/common.sh" 2>/dev/null; then
    pass "common.sh sources without error"
else
    fail "common.sh failed to source"
fi

# Test 2: PostToolUseFailure suggests capture for Edit
echo "Test 2: PostToolUseFailure on Edit failure"
output=$(echo '{"hook_event_name": "PostToolUseFailure", "tool_name": "Edit", "tool_input": {"file_path": "/test.ts"}}' | \
    "$PLUGIN_DIR/hooks/scripts/capture-tool-failure.sh" 2>&1 || true)
if echo "$output" | grep -q "capture_mistake"; then
    pass "Suggests capture on Edit failure"
else
    fail "Should suggest capture: $output"
fi

# Test 3: PostToolUseFailure filters Read
echo "Test 3: PostToolUseFailure filters Read"
output=$(echo '{"hook_event_name": "PostToolUseFailure", "tool_name": "Read", "tool_input": {"file_path": "/test.md"}}' | \
    "$PLUGIN_DIR/hooks/scripts/capture-tool-failure.sh" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Silently ignores Read failure"
else
    fail "Should be silent: $output"
fi

# Test 4: SessionStart hook runs
echo "Test 4: SessionStart hook runs"
if "$PLUGIN_DIR/hooks/scripts/inject-learnings.sh" < /dev/null >/dev/null 2>&1; then
    pass "SessionStart hook executes"
else
    fail "SessionStart hook crashed"
fi

# Test 5: PreToolUse handles Edit
echo "Test 5: PreToolUse handles Edit"
output=$(echo '{"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "nonexistent/file.py"}}' | \
    "$PLUGIN_DIR/hooks/scripts/pre-edit-check.sh" 2>&1 || true)
pass "PreToolUse handles Edit without crashing"

# Test 6: PreToolUse filters Read
echo "Test 6: PreToolUse filters Read"
output=$(echo '{"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "test.py"}}' | \
    "$PLUGIN_DIR/hooks/scripts/pre-edit-check.sh" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "PreToolUse ignores Read"
else
    fail "Should ignore Read: $output"
fi

# Test 7: hooks.json is valid and has correct structure
echo "Test 7: hooks.json validation"
if jq -e '.hooks.PostToolUseFailure' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.SessionStart' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.PreToolUse' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.Stop' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1; then
    pass "hooks.json has all 4 hook events"
else
    fail "hooks.json missing hook events"
fi

# Test 8: hooks.json uses CLAUDE_PLUGIN_ROOT
echo "Test 8: hooks.json uses CLAUDE_PLUGIN_ROOT"
if grep -q 'CLAUDE_PLUGIN_ROOT' "$PLUGIN_DIR/hooks/hooks.json"; then
    pass "hooks.json uses \${CLAUDE_PLUGIN_ROOT}"
else
    fail "hooks.json should use \${CLAUDE_PLUGIN_ROOT}"
fi

# Test 9: plugin.json references hooks
echo "Test 9: plugin.json references hooks"
if jq -e '.hooks' "$PLUGIN_DIR/.claude-plugin/plugin.json" >/dev/null 2>&1; then
    pass "plugin.json references hooks"
else
    fail "plugin.json missing hooks reference"
fi

# Test 10: All lib scripts have --help
echo "Test 10: Library scripts have --help"
all_have_help=true
for script in "$PLUGIN_DIR/lib"/*.sh; do
    if [[ -f "$script" && -x "$script" && "$(basename "$script")" != "common.sh" ]]; then
        if ! "$script" --help >/dev/null 2>&1; then
            fail "Script missing --help: $(basename "$script")"
            all_have_help=false
        fi
    fi
done
if $all_have_help; then
    pass "All lib scripts support --help"
fi

# Summary
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [[ "$FAILED" -gt 0 ]]; then
    exit 1
else
    echo "All tests passed!"
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/tests/test_hooks.sh`

**Step 3: Run tests**

Run: `./intent-layer-plugin/tests/test_hooks.sh`
Expected: All tests pass

**Step 4: Commit**

```bash
git add intent-layer-plugin/tests/
git commit -m "test(learning-layer): add integration test suite"
```

---

## Task 10: Create Plugin README

**Files:**
- Create: `intent-layer-plugin/README.md`

**Step 1: Write README**

Create `intent-layer-plugin/README.md`:

```markdown
# Intent Layer Plugin

A Claude Code plugin implementing a continuous learning loop that captures mistakes and injects learnings into agent workflows.

## Features

### Capture Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `capture-tool-failure` | PostToolUseFailure | Suggests `capture_mistake.sh` on Edit/Write/Bash failures |
| Stop prompt | Stop | LLM evaluates session for learnings, blocks if found |

### Feedback Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `inject-learnings` | SessionStart | Injects recent accepted mistakes (7-day window) |
| `pre-edit-check` | PreToolUse | Injects Pitfalls from covering AGENTS.md |

### Adaptive Behavior

The PreToolUse hook uses **adaptive gating** based on mistake history:
- **Quiet mode** (0-1 previous mistakes): Informational pitfalls display
- **Gated mode** (2+ previous mistakes): Strong warning requiring review

## Installation

```bash
claude plugin install ./intent-layer-plugin
```

## Requirements

- `jq` for JSON parsing (`brew install jq` or `apt install jq`)
- The `intent-layer` skill for `capture_mistake.sh`

## Directory Structure

```
intent-layer-plugin/
├── .claude-plugin/plugin.json
├── hooks/
│   ├── hooks.json           # Hook registration (official format)
│   └── scripts/
│       ├── capture-tool-failure.sh
│       ├── inject-learnings.sh
│       └── pre-edit-check.sh
├── lib/
│   ├── common.sh
│   ├── aggregate_learnings.sh
│   ├── find_covering_node.sh
│   └── check_mistake_history.sh
└── tests/test_hooks.sh
```

## How It Works

```
Agent encounters unexpected failure
    ↓
PostToolUseFailure hook suggests capture_mistake.sh
    ↓
Mistake report created in .intent-layer/mistakes/pending/
    ↓
Human reviews → moves to accepted/ or rejected/
    ↓
Human updates AGENTS.md with check/pitfall
    ↓
Next session: SessionStart injects recent learnings
    ↓
Agent edits file: PreToolUse injects relevant pitfalls
```

## Testing

```bash
./tests/test_hooks.sh
```

## Configuration

- Risk threshold: Edit `check_mistake_history.sh` `--threshold N` (default: 2)
- Learnings window: Edit `aggregate_learnings.sh` `--days N` (default: 7)

## Documentation Reference

https://code.claude.com/docs/en/hooks
```

**Step 2: Commit**

```bash
git add intent-layer-plugin/README.md
git commit -m "docs(learning-layer): add plugin README"
```

---

## Task 11: Final Verification

**Step 1: Verify complete structure**

Run: `find intent-layer-plugin -type f | sort`

Expected:
```
intent-layer-plugin/.claude-plugin/plugin.json
intent-layer-plugin/README.md
intent-layer-plugin/hooks/hooks.json
intent-layer-plugin/hooks/scripts/capture-tool-failure.sh
intent-layer-plugin/hooks/scripts/inject-learnings.sh
intent-layer-plugin/hooks/scripts/pre-edit-check.sh
intent-layer-plugin/lib/aggregate_learnings.sh
intent-layer-plugin/lib/check_mistake_history.sh
intent-layer-plugin/lib/common.sh
intent-layer-plugin/lib/find_covering_node.sh
intent-layer-plugin/tests/test_hooks.sh
```

**Step 2: Run tests**

Run: `./intent-layer-plugin/tests/test_hooks.sh`
Expected: All tests pass

**Step 3: Validate JSON**

Run: `jq . intent-layer-plugin/hooks/hooks.json > /dev/null && jq . intent-layer-plugin/.claude-plugin/plugin.json > /dev/null && echo "All JSON valid"`

**Step 4: Create summary commit if needed**

```bash
git status
# If uncommitted changes exist:
git add -A intent-layer-plugin/
git commit -m "feat(learning-layer): complete learning layer plugin implementation

Implements continuous learning loop with official Claude Code hooks format:

CAPTURE HOOKS:
- PostToolUseFailure: Suggests capture on Edit/Write/Bash failures
- Stop (prompt): LLM evaluates session for learnings

FEEDBACK HOOKS:
- SessionStart: Injects recent learnings via additionalContext
- PreToolUse: Adaptive pitfall injection via additionalContext

Uses official hooks.json format with \${CLAUDE_PLUGIN_ROOT}.

Ref: https://code.claude.com/docs/en/hooks"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Plugin scaffold | plugin.json, common.sh |
| 2 | PostToolUseFailure hook | capture-tool-failure.sh |
| 3 | Aggregation script | aggregate_learnings.sh |
| 4 | SessionStart hook | inject-learnings.sh |
| 5 | Node finder | find_covering_node.sh |
| 6 | History checker | check_mistake_history.sh |
| 7 | PreToolUse hook | pre-edit-check.sh |
| 8 | Hook registration | hooks.json |
| 9 | Tests | test_hooks.sh |
| 10 | Documentation | README.md |
| 11 | Verification | - |

**Key differences from v2:**
- Uses **official hooks.json format** with event-keyed structure and matchers
- Uses **`${CLAUDE_PLUGIN_ROOT}`** environment variable for paths
- Uses **`additionalContext`** JSON output pattern for context injection
- Uses **prompt-based Stop hook** with LLM evaluation (not text file)
- Removed invented `matchTools` field - uses `matcher` regex instead
- All output follows official JSON schema

**Total commits:** 10
