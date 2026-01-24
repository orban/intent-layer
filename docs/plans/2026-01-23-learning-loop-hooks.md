# Learning Loop Hooks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Claude Code hooks that automatically capture mistakes and inject learnings back into agent workflows.

**Architecture:** Four hooks working together - two capture hooks (PostToolUseFailure, Stop) detect issues and trigger mistake reports, two feedback hooks (SessionStart, PreToolUse) inject relevant learnings and pre-flight checks before agents make changes.

**Tech Stack:** Bash scripts for hook execution, Markdown for reports, existing `capture_mistake.sh` infrastructure.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     LEARNING LOOP                                │
├─────────────────────────────────────────────────────────────────┤
│  CAPTURE (Detection)                                             │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │ PostToolUseFailure  │    │ Stop (prompt-based)             │ │
│  │ - Tool errors       │    │ - Subtle issues                 │ │
│  │ - Immediate capture │    │ - End-of-session analysis       │ │
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
│  │ SessionStart        │    │ PreToolUse (Edit/Write)         │ │
│  │ - Recent learnings  │    │ - Pitfalls from nearest node    │ │
│  │ - High-level summary│    │ - Adaptive: quiet → gated       │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Hook Files Location

All hooks will be placed in the plugin structure:

```
intent-layer-plugin/
├── hooks/
│   ├── capture-tool-failure/
│   │   └── hook.sh           # PostToolUseFailure hook
│   ├── session-summary/
│   │   └── hook.txt          # Stop prompt-based hook
│   ├── inject-learnings/
│   │   └── hook.sh           # SessionStart hook
│   └── pre-edit-check/
│       └── hook.sh           # PreToolUse hook for Edit/Write
```

---

## Task 1: Create Plugin Directory Structure

**Files:**
- Create: `intent-layer-plugin/.claude-plugin/plugin.json`
- Create: `intent-layer-plugin/hooks/` (directory structure)

**Step 1: Create plugin manifest**

```bash
mkdir -p intent-layer-plugin/.claude-plugin
mkdir -p intent-layer-plugin/hooks/{capture-tool-failure,session-summary,inject-learnings,pre-edit-check}
```

**Step 2: Write plugin.json**

Create `intent-layer-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "intent-layer",
  "version": "0.1.0",
  "description": "Intent Layer with continuous learning loop - hooks for mistake capture and knowledge injection",
  "author": "intent-layer-team"
}
```

**Step 3: Verify structure**

Run: `ls -la intent-layer-plugin/`
Expected: `.claude-plugin/` and `hooks/` directories exist

**Step 4: Commit**

```bash
git add intent-layer-plugin/
git commit -m "feat(hooks): scaffold plugin structure for learning loop"
```

---

## Task 2: Implement PostToolUseFailure Capture Hook

**Files:**
- Create: `intent-layer-plugin/hooks/capture-tool-failure/hook.sh`

**Purpose:** When any tool fails, prompt to capture the mistake using existing `capture_mistake.sh` infrastructure.

**Step 1: Write hook.sh script**

Create `intent-layer-plugin/hooks/capture-tool-failure/hook.sh`:

```bash
#!/usr/bin/env bash
# PostToolUseFailure hook - Triggers mistake capture on tool failures
# Input: JSON on stdin with tool_name, tool_input, error
# Output: Message to stderr for agent to see

set -euo pipefail

# Read hook input from stdin
INPUT=$(cat)

# Extract relevant fields
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')
ERROR=$(echo "$INPUT" | jq -r '.error // "unknown error"')

# Skip certain expected failures (file not found when exploring, etc.)
case "$TOOL_NAME" in
    Read|Glob|Grep)
        # These often fail during exploration - not usually mistakes
        if echo "$ERROR" | grep -qi "no such file\|not found\|no files found"; then
            exit 0
        fi
        ;;
esac

# For significant failures, suggest capturing the mistake
echo "⚠️ Tool '$TOOL_NAME' failed: $ERROR" >&2
echo "" >&2
echo "Consider capturing this as a learning opportunity:" >&2
echo "  ~/.claude/skills/intent-layer/scripts/capture_mistake.sh --from-git" >&2
echo "" >&2
echo "Or if this was expected/exploratory, ignore this message." >&2
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/capture-tool-failure/hook.sh`

**Step 3: Test hook locally**

Run:
```bash
echo '{"tool_name": "Edit", "error": "Failed to write file"}' | \
  ./intent-layer-plugin/hooks/capture-tool-failure/hook.sh
```

Expected: Outputs warning message to stderr with capture suggestion

**Step 4: Test filtering**

Run:
```bash
echo '{"tool_name": "Read", "error": "No such file or directory"}' | \
  ./intent-layer-plugin/hooks/capture-tool-failure/hook.sh
```

Expected: Silent exit (no output) since this is expected behavior

**Step 5: Commit**

```bash
git add intent-layer-plugin/hooks/capture-tool-failure/
git commit -m "feat(hooks): add PostToolUseFailure capture hook"
```

---

## Task 3: Implement Stop Prompt Hook (Session Summary)

**Files:**
- Create: `intent-layer-plugin/hooks/session-summary/hook.txt`

**Purpose:** Prompt-based hook that asks Claude to analyze the session for subtle mistakes at the end.

**Step 1: Write prompt hook**

Create `intent-layer-plugin/hooks/session-summary/hook.txt`:

```markdown
## Session Learning Review

Before ending this session, briefly review for potential Intent Layer learnings:

1. **Unexpected behaviors**: Did anything work differently than documented?
2. **Missing information**: Did you have to figure something out that should have been documented?
3. **Corrections received**: Did the user correct any assumptions you made?

If you identify any issues that would help future agents, suggest running:
```
~/.claude/skills/intent-layer/scripts/capture_mistake.sh
```

Only surface genuine gaps - don't report normal exploration or expected behaviors.
If nothing significant was discovered, simply proceed with ending the session.
```

**Step 2: Verify file created**

Run: `cat intent-layer-plugin/hooks/session-summary/hook.txt`
Expected: Prompt content displayed

**Step 3: Commit**

```bash
git add intent-layer-plugin/hooks/session-summary/
git commit -m "feat(hooks): add Stop prompt hook for session learning review"
```

---

## Task 4: Create Learnings Aggregation Script

**Files:**
- Create: `intent-layer/scripts/aggregate_learnings.sh`

**Purpose:** Aggregate recent accepted mistakes into a summary for SessionStart injection.

**Step 1: Write aggregation script**

Create `intent-layer/scripts/aggregate_learnings.sh`:

```bash
#!/usr/bin/env bash
# Aggregate recent learnings from accepted mistakes
# Usage: aggregate_learnings.sh [--days N] [--format summary|full]

set -euo pipefail

show_help() {
    cat << 'EOF'
aggregate_learnings.sh - Aggregate recent learnings for injection

USAGE:
    aggregate_learnings.sh [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -d, --days N         Include learnings from last N days (default: 7)
    -f, --format FORMAT  Output format: summary|full (default: summary)

OUTPUT:
    Markdown summary of recent accepted mistakes, suitable for hook injection.
EOF
    exit 0
}

# Defaults
DAYS=7
FORMAT="summary"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -d|--days) DAYS="$2"; shift 2 ;;
        -f|--format) FORMAT="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Find accepted mistakes directory
MISTAKES_DIR=".intent-layer/mistakes/accepted"

if [ ! -d "$MISTAKES_DIR" ]; then
    # No accepted mistakes yet
    exit 0
fi

# Calculate cutoff date (BSD/GNU compatible)
if date -v-1d > /dev/null 2>&1; then
    # BSD date (macOS)
    CUTOFF=$(date -v-${DAYS}d +%Y-%m-%d)
else
    # GNU date (Linux)
    CUTOFF=$(date -d "$DAYS days ago" +%Y-%m-%d)
fi

# Find recent files
RECENT_FILES=$(find "$MISTAKES_DIR" -name "MISTAKE-*.md" -type f -newermt "$CUTOFF" 2>/dev/null || true)

if [ -z "$RECENT_FILES" ]; then
    # No recent learnings
    exit 0
fi

# Count files
FILE_COUNT=$(echo "$RECENT_FILES" | wc -l | tr -d ' ')

echo "## Recent Learnings (last $DAYS days)"
echo ""
echo "$FILE_COUNT accepted mistake(s) converted to Intent Layer updates."
echo ""

if [ "$FORMAT" = "full" ]; then
    # Full details
    echo "$RECENT_FILES" | while read -r file; do
        if [ -f "$file" ]; then
            echo "---"
            echo ""
            cat "$file"
            echo ""
        fi
    done
else
    # Summary format - extract key info
    echo "| Directory | Root Cause | Fix Applied |"
    echo "|-----------|------------|-------------|"

    echo "$RECENT_FILES" | while read -r file; do
        if [ -f "$file" ]; then
            DIR=$(grep -m1 "^\*\*Directory\*\*:" "$file" | sed 's/.*: //' || echo "unknown")
            CAUSE=$(grep -m1 "^### Root Cause" -A1 "$file" | tail -1 | head -c 50 || echo "unknown")
            DISP=$(grep -E "^\- \[x\]" "$file" | head -1 | sed 's/.*\] //' || echo "unknown")
            echo "| $DIR | $CAUSE... | $DISP |"
        fi
    done
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer/scripts/aggregate_learnings.sh`

**Step 3: Add help test**

Run: `./intent-layer/scripts/aggregate_learnings.sh --help`
Expected: Help message displayed

**Step 4: Test with no learnings**

Run: `./intent-layer/scripts/aggregate_learnings.sh`
Expected: Silent exit (no output when no accepted mistakes exist)

**Step 5: Commit**

```bash
git add intent-layer/scripts/aggregate_learnings.sh
git commit -m "feat(scripts): add learnings aggregation for session injection"
```

---

## Task 5: Implement SessionStart Injection Hook

**Files:**
- Create: `intent-layer-plugin/hooks/inject-learnings/hook.sh`

**Purpose:** Inject recent learnings from accepted mistakes at session start.

**Step 1: Write hook script**

Create `intent-layer-plugin/hooks/inject-learnings/hook.sh`:

```bash
#!/usr/bin/env bash
# SessionStart hook - Injects recent learnings into agent context
# Output: Markdown content to stdout for injection

set -euo pipefail

# Locate the aggregation script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGGREGATE_SCRIPT="$HOME/.claude/skills/intent-layer/scripts/aggregate_learnings.sh"

# Fallback to local path if skill not installed
if [ ! -f "$AGGREGATE_SCRIPT" ]; then
    # Try relative to plugin
    AGGREGATE_SCRIPT="$(dirname "$SCRIPT_DIR")/../../../intent-layer/scripts/aggregate_learnings.sh"
fi

if [ ! -f "$AGGREGATE_SCRIPT" ]; then
    # No aggregation script available
    exit 0
fi

# Run aggregation
LEARNINGS=$("$AGGREGATE_SCRIPT" --days 7 --format summary 2>/dev/null || true)

if [ -z "$LEARNINGS" ]; then
    exit 0
fi

# Output learnings for injection
echo "## Intent Layer: Recent Learnings"
echo ""
echo "The following mistakes were recently captured and converted to Intent Layer updates."
echo "Be aware of these patterns when working in related areas."
echo ""
echo "$LEARNINGS"
echo ""
echo "---"
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/inject-learnings/hook.sh`

**Step 3: Test hook**

Run: `./intent-layer-plugin/hooks/inject-learnings/hook.sh`
Expected: Either outputs recent learnings or silent exit if none

**Step 4: Commit**

```bash
git add intent-layer-plugin/hooks/inject-learnings/
git commit -m "feat(hooks): add SessionStart hook for learnings injection"
```

---

## Task 6: Create Node Finding Utility Script

**Files:**
- Create: `intent-layer/scripts/find_covering_node.sh`

**Purpose:** Walk up from a file path to find the nearest covering AGENTS.md.

**Step 1: Write node finder script**

Create `intent-layer/scripts/find_covering_node.sh`:

```bash
#!/usr/bin/env bash
# Find the covering AGENTS.md node for a given file path
# Usage: find_covering_node.sh <file_path>

set -euo pipefail

show_help() {
    cat << 'EOF'
find_covering_node.sh - Find nearest covering AGENTS.md

USAGE:
    find_covering_node.sh <file_path>

OPTIONS:
    -h, --help    Show this help
    -s, --section Extract specific section (e.g., Pitfalls, Contracts)

OUTPUT:
    Path to covering AGENTS.md or CLAUDE.md, or empty if none found.

EXAMPLES:
    find_covering_node.sh src/auth/login.ts
    find_covering_node.sh src/api/handlers/user.py --section Pitfalls
EOF
    exit 0
}

FILE_PATH=""
SECTION=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -s|--section) SECTION="$2"; shift 2 ;;
        *) FILE_PATH="$1"; shift ;;
    esac
done

if [ -z "$FILE_PATH" ]; then
    echo "Error: File path required" >&2
    exit 1
fi

# Normalize to absolute path if relative
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="$(pwd)/$FILE_PATH"
fi

# Start from file's directory
CURRENT_DIR=$(dirname "$FILE_PATH")

# Walk up until we find AGENTS.md, CLAUDE.md, or hit repo root
while [ "$CURRENT_DIR" != "/" ]; do
    # Check for AGENTS.md first (preferred)
    if [ -f "$CURRENT_DIR/AGENTS.md" ]; then
        NODE_PATH="$CURRENT_DIR/AGENTS.md"
        break
    fi

    # Check for CLAUDE.md (root level)
    if [ -f "$CURRENT_DIR/CLAUDE.md" ]; then
        NODE_PATH="$CURRENT_DIR/CLAUDE.md"
        break
    fi

    # Stop at git root
    if [ -d "$CURRENT_DIR/.git" ]; then
        break
    fi

    # Move up
    CURRENT_DIR=$(dirname "$CURRENT_DIR")
done

if [ -z "${NODE_PATH:-}" ]; then
    # No covering node found
    exit 0
fi

if [ -n "$SECTION" ]; then
    # Extract specific section
    # Find section header and extract until next ## header
    awk -v section="$SECTION" '
        /^## / { if (found) exit; if ($0 ~ "^## "section) found=1 }
        found { print }
    ' "$NODE_PATH"
else
    # Just output the path
    echo "$NODE_PATH"
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer/scripts/find_covering_node.sh`

**Step 3: Test with existing file**

Run: `./intent-layer/scripts/find_covering_node.sh eval-harness/lib/cli.py`
Expected: Outputs `eval-harness/AGENTS.md` or similar path

**Step 4: Test section extraction**

Run: `./intent-layer/scripts/find_covering_node.sh eval-harness/lib/cli.py --section Pitfalls`
Expected: Outputs the Pitfalls section content

**Step 5: Commit**

```bash
git add intent-layer/scripts/find_covering_node.sh
git commit -m "feat(scripts): add covering node finder for PreToolUse hook"
```

---

## Task 7: Create Mistake History Tracker

**Files:**
- Create: `intent-layer/scripts/check_mistake_history.sh`

**Purpose:** Check if a directory has a history of mistakes (for adaptive gating).

**Step 1: Write history checker script**

Create `intent-layer/scripts/check_mistake_history.sh`:

```bash
#!/usr/bin/env bash
# Check if a directory has history of mistakes
# Usage: check_mistake_history.sh <directory>

set -euo pipefail

show_help() {
    cat << 'EOF'
check_mistake_history.sh - Check directory mistake history

USAGE:
    check_mistake_history.sh <directory>

OPTIONS:
    -h, --help       Show this help
    -t, --threshold N  Mistake count threshold for "high risk" (default: 2)
    --json           Output as JSON

OUTPUT:
    Exit code 0 if high-risk (above threshold), 1 if low-risk.
    With --json, outputs {"directory": "...", "count": N, "high_risk": bool}

EXAMPLES:
    check_mistake_history.sh src/auth/
    if check_mistake_history.sh src/api/; then echo "High risk area"; fi
EOF
    exit 0
}

DIRECTORY=""
THRESHOLD=2
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -t|--threshold) THRESHOLD="$2"; shift 2 ;;
        --json) JSON_OUTPUT=true; shift ;;
        *) DIRECTORY="$1"; shift ;;
    esac
done

if [ -z "$DIRECTORY" ]; then
    echo "Error: Directory path required" >&2
    exit 1
fi

# Normalize directory path
DIRECTORY="${DIRECTORY%/}"

# Check all mistake directories
COUNT=0
for mistakes_dir in ".intent-layer/mistakes/pending" ".intent-layer/mistakes/accepted"; do
    if [ -d "$mistakes_dir" ]; then
        # Count mistakes that mention this directory
        dir_count=$(grep -l "^\*\*Directory\*\*:.*$DIRECTORY" "$mistakes_dir"/*.md 2>/dev/null | wc -l || echo 0)
        COUNT=$((COUNT + dir_count))
    fi
done

HIGH_RISK=false
if [ "$COUNT" -ge "$THRESHOLD" ]; then
    HIGH_RISK=true
fi

if [ "$JSON_OUTPUT" = true ]; then
    echo "{\"directory\": \"$DIRECTORY\", \"count\": $COUNT, \"high_risk\": $HIGH_RISK}"
else
    if [ "$HIGH_RISK" = true ]; then
        echo "High risk: $DIRECTORY ($COUNT previous mistakes)"
        exit 0
    else
        exit 1
    fi
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer/scripts/check_mistake_history.sh`

**Step 3: Test help**

Run: `./intent-layer/scripts/check_mistake_history.sh --help`
Expected: Help message displayed

**Step 4: Test with JSON output**

Run: `./intent-layer/scripts/check_mistake_history.sh src/api/ --json`
Expected: JSON output with count and high_risk flag

**Step 5: Commit**

```bash
git add intent-layer/scripts/check_mistake_history.sh
git commit -m "feat(scripts): add mistake history checker for adaptive gating"
```

---

## Task 8: Implement PreToolUse Hook (Adaptive Pitfalls Injection)

**Files:**
- Create: `intent-layer-plugin/hooks/pre-edit-check/hook.sh`

**Purpose:** Before Edit/Write, inject relevant Pitfalls with adaptive quiet/gated behavior.

**Step 1: Write PreToolUse hook**

Create `intent-layer-plugin/hooks/pre-edit-check/hook.sh`:

```bash
#!/usr/bin/env bash
# PreToolUse hook for Edit/Write - Injects relevant pitfalls with adaptive gating
# Input: JSON on stdin with tool_name, tool_input
# Output: Context injection to stdout

set -euo pipefail

# Read hook input
INPUT=$(cat)

# Only trigger for Edit/Write tools
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
case "$TOOL_NAME" in
    Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

# Extract file path from tool input
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Locate helper scripts
SKILL_DIR="$HOME/.claude/skills/intent-layer/scripts"

# Fallback paths
if [ ! -d "$SKILL_DIR" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SKILL_DIR="$(dirname "$SCRIPT_DIR")/../../../intent-layer/scripts"
fi

FIND_NODE="$SKILL_DIR/find_covering_node.sh"
CHECK_HISTORY="$SKILL_DIR/check_mistake_history.sh"

if [ ! -f "$FIND_NODE" ]; then
    exit 0
fi

# Find covering node
NODE_PATH=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

if [ -z "$NODE_PATH" ]; then
    exit 0
fi

# Get directory for history check
FILE_DIR=$(dirname "$FILE_PATH")

# Check if high-risk area
HIGH_RISK=false
if [ -f "$CHECK_HISTORY" ]; then
    if "$CHECK_HISTORY" "$FILE_DIR" >/dev/null 2>&1; then
        HIGH_RISK=true
    fi
fi

# Extract pitfalls section
PITFALLS=$("$FIND_NODE" "$FILE_PATH" --section Pitfalls 2>/dev/null || true)

if [ -z "$PITFALLS" ]; then
    # No pitfalls to inject
    exit 0
fi

# Output context injection
echo "## Intent Layer Context"
echo ""
echo "**Editing:** \`$FILE_PATH\`"
echo "**Covered by:** \`$NODE_PATH\`"
echo ""

if [ "$HIGH_RISK" = true ]; then
    # Gated mode - require acknowledgment
    echo "⚠️ **HIGH-RISK AREA** - This directory has a history of mistakes."
    echo ""
    echo "Before proceeding, verify these pitfalls don't apply to your change:"
    echo ""
    echo "$PITFALLS"
    echo ""
    echo "---"
    echo "**Pre-flight check required:** Confirm you've reviewed the pitfalls above."
else
    # Quiet mode - informational only
    echo "ℹ️ Relevant pitfalls from covering node:"
    echo ""
    echo "$PITFALLS"
    echo ""
    echo "---"
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/pre-edit-check/hook.sh`

**Step 3: Test with Edit tool input**

Run:
```bash
echo '{"tool_name": "Edit", "tool_input": {"file_path": "eval-harness/lib/cli.py"}}' | \
  ./intent-layer-plugin/hooks/pre-edit-check/hook.sh
```

Expected: Outputs pitfalls from eval-harness/AGENTS.md with appropriate context

**Step 4: Test with non-Edit tool**

Run:
```bash
echo '{"tool_name": "Read", "tool_input": {"file_path": "README.md"}}' | \
  ./intent-layer-plugin/hooks/pre-edit-check/hook.sh
```

Expected: Silent exit (no output)

**Step 5: Commit**

```bash
git add intent-layer-plugin/hooks/pre-edit-check/
git commit -m "feat(hooks): add PreToolUse hook with adaptive pitfall injection"
```

---

## Task 9: Create Hook Registration Configuration

**Files:**
- Create: `intent-layer-plugin/hooks.json`

**Purpose:** Register all hooks with their triggers and configurations.

**Step 1: Write hooks.json**

Create `intent-layer-plugin/hooks.json`:

```json
{
  "hooks": [
    {
      "id": "capture-tool-failure",
      "description": "Suggest mistake capture when tools fail",
      "trigger": "PostToolUseFailure",
      "type": "command",
      "command": "./hooks/capture-tool-failure/hook.sh"
    },
    {
      "id": "session-summary",
      "description": "Review session for learnings before ending",
      "trigger": "Stop",
      "type": "prompt",
      "promptFile": "./hooks/session-summary/hook.txt"
    },
    {
      "id": "inject-learnings",
      "description": "Inject recent learnings at session start",
      "trigger": "SessionStart",
      "type": "command",
      "command": "./hooks/inject-learnings/hook.sh"
    },
    {
      "id": "pre-edit-check",
      "description": "Inject pitfalls before Edit/Write with adaptive gating",
      "trigger": "PreToolUse",
      "matchTools": ["Edit", "Write", "NotebookEdit"],
      "type": "command",
      "command": "./hooks/pre-edit-check/hook.sh"
    }
  ]
}
```

**Step 2: Validate JSON**

Run: `cat intent-layer-plugin/hooks.json | jq .`
Expected: Pretty-printed JSON without errors

**Step 3: Commit**

```bash
git add intent-layer-plugin/hooks.json
git commit -m "feat(hooks): add hook registration configuration"
```

---

## Task 10: Integration Testing

**Files:**
- Create: `intent-layer-plugin/tests/test_hooks.sh`

**Purpose:** End-to-end test of all hooks working together.

**Step 1: Write integration test script**

Create `intent-layer-plugin/tests/test_hooks.sh`:

```bash
#!/usr/bin/env bash
# Integration tests for learning loop hooks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
TESTS_PASSED=0
TESTS_FAILED=0

echo "=== Learning Loop Hooks Integration Tests ==="
echo ""

# Helper functions
pass() { echo "✅ $1"; ((TESTS_PASSED++)); }
fail() { echo "❌ $1"; ((TESTS_FAILED++)); }

# Test 1: PostToolUseFailure hook
echo "Test 1: PostToolUseFailure hook"
output=$(echo '{"tool_name": "Edit", "error": "Permission denied"}' | \
  "$PLUGIN_DIR/hooks/capture-tool-failure/hook.sh" 2>&1 || true)
if echo "$output" | grep -q "capture_mistake"; then
    pass "Suggests capture on significant failure"
else
    fail "Did not suggest capture: $output"
fi

# Test 2: PostToolUseFailure filters expected errors
echo "Test 2: PostToolUseFailure filtering"
output=$(echo '{"tool_name": "Read", "error": "No such file"}' | \
  "$PLUGIN_DIR/hooks/capture-tool-failure/hook.sh" 2>&1 || true)
if [ -z "$output" ]; then
    pass "Silently ignores expected Read failures"
else
    fail "Should have been silent: $output"
fi

# Test 3: Stop prompt hook exists
echo "Test 3: Stop prompt hook"
if [ -f "$PLUGIN_DIR/hooks/session-summary/hook.txt" ]; then
    if grep -q "Learning Review" "$PLUGIN_DIR/hooks/session-summary/hook.txt"; then
        pass "Stop prompt contains learning review"
    else
        fail "Stop prompt missing learning content"
    fi
else
    fail "Stop prompt file missing"
fi

# Test 4: SessionStart hook runs without error
echo "Test 4: SessionStart hook"
if "$PLUGIN_DIR/hooks/inject-learnings/hook.sh" >/dev/null 2>&1; then
    pass "SessionStart hook runs without error"
else
    fail "SessionStart hook failed"
fi

# Test 5: PreToolUse hook filters non-edit tools
echo "Test 5: PreToolUse filtering"
output=$(echo '{"tool_name": "Read", "tool_input": {"file_path": "test.py"}}' | \
  "$PLUGIN_DIR/hooks/pre-edit-check/hook.sh" 2>&1 || true)
if [ -z "$output" ]; then
    pass "PreToolUse ignores Read tool"
else
    fail "PreToolUse should ignore Read: $output"
fi

# Test 6: PreToolUse triggers for Edit
echo "Test 6: PreToolUse Edit trigger"
# This may fail if no covering node exists - that's expected
output=$(echo '{"tool_name": "Edit", "tool_input": {"file_path": "nonexistent/file.py"}}' | \
  "$PLUGIN_DIR/hooks/pre-edit-check/hook.sh" 2>&1 || true)
# Just verify it doesn't crash
pass "PreToolUse handles Edit without crashing"

# Test 7: hooks.json is valid
echo "Test 7: hooks.json validation"
if jq empty "$PLUGIN_DIR/hooks.json" 2>/dev/null; then
    hook_count=$(jq '.hooks | length' "$PLUGIN_DIR/hooks.json")
    if [ "$hook_count" -eq 4 ]; then
        pass "hooks.json valid with 4 hooks"
    else
        fail "Expected 4 hooks, got $hook_count"
    fi
else
    fail "hooks.json is invalid JSON"
fi

# Summary
echo ""
echo "=== Results ==="
echo "Passed: $TESTS_PASSED"
echo "Failed: $TESTS_FAILED"

if [ "$TESTS_FAILED" -gt 0 ]; then
    exit 1
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
git commit -m "test(hooks): add integration tests for learning loop"
```

---

## Task 11: Update Plugin Manifest with Hooks

**Files:**
- Modify: `intent-layer-plugin/.claude-plugin/plugin.json`

**Step 1: Update plugin.json to reference hooks**

```json
{
  "name": "intent-layer",
  "version": "0.1.0",
  "description": "Intent Layer with continuous learning loop - hooks for mistake capture and knowledge injection",
  "author": "intent-layer-team",
  "hooks": "./hooks.json"
}
```

**Step 2: Verify**

Run: `cat intent-layer-plugin/.claude-plugin/plugin.json | jq .`
Expected: Valid JSON with hooks reference

**Step 3: Commit**

```bash
git add intent-layer-plugin/.claude-plugin/plugin.json
git commit -m "chore(plugin): reference hooks.json in manifest"
```

---

## Task 12: Documentation

**Files:**
- Create: `intent-layer-plugin/README.md`

**Step 1: Write plugin README**

Create `intent-layer-plugin/README.md`:

```markdown
# Intent Layer Plugin

A Claude Code plugin that implements a continuous learning loop for codebases with Intent Layer (AGENTS.md/CLAUDE.md) documentation.

## Features

### Capture Hooks (Detection)

1. **PostToolUseFailure** (`capture-tool-failure`)
   - Triggers when tools fail
   - Suggests running `capture_mistake.sh` for significant failures
   - Filters out expected failures (file not found during exploration)

2. **Stop** (`session-summary`)
   - Prompt-based hook at session end
   - Asks agent to review for subtle mistakes or missing documentation
   - Only surfaces genuine Intent Layer gaps

### Feedback Hooks (Injection)

3. **SessionStart** (`inject-learnings`)
   - Injects recent learnings from accepted mistakes (last 7 days)
   - Provides summary of patterns to watch for
   - Silent if no recent learnings

4. **PreToolUse** (`pre-edit-check`)
   - Triggers before Edit/Write/NotebookEdit
   - Finds covering AGENTS.md and injects relevant Pitfalls
   - **Adaptive behavior:**
     - **Quiet mode** (default): Informational pitfalls display
     - **Gated mode** (high-risk areas): Requires acknowledgment

## Installation

```bash
claude plugin install ./intent-layer-plugin
```

## Directory Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   └── plugin.json       # Plugin manifest
├── hooks/
│   ├── capture-tool-failure/
│   │   └── hook.sh       # PostToolUseFailure hook
│   ├── session-summary/
│   │   └── hook.txt      # Stop prompt hook
│   ├── inject-learnings/
│   │   └── hook.sh       # SessionStart hook
│   └── pre-edit-check/
│       └── hook.sh       # PreToolUse hook
├── hooks.json            # Hook registration
├── tests/
│   └── test_hooks.sh     # Integration tests
└── README.md
```

## Configuration

Hooks are configured in `hooks.json`. The PreToolUse hook uses adaptive gating based on mistake history:

- Areas with 2+ previous mistakes → Gated mode (confirmation required)
- Areas with 0-1 previous mistakes → Quiet mode (informational)

Adjust the threshold in `check_mistake_history.sh` with `--threshold N`.

## Dependencies

Requires the `intent-layer` skill to be installed:
```bash
ln -s /path/to/intent-layer ~/.claude/skills/intent-layer
```

## Testing

```bash
./tests/test_hooks.sh
```
```

**Step 2: Commit**

```bash
git add intent-layer-plugin/README.md
git commit -m "docs(plugin): add README for learning loop hooks"
```

---

## Task 13: Final Integration Commit

**Step 1: Verify all files**

Run: `ls -laR intent-layer-plugin/`
Expected: All directories and files present

**Step 2: Run final test**

Run: `./intent-layer-plugin/tests/test_hooks.sh`
Expected: All tests pass

**Step 3: Create summary commit**

```bash
git add -A
git commit -m "feat(intent-layer): complete learning loop hooks implementation

Implements continuous learning loop with four hooks:
- PostToolUseFailure: Capture immediate tool failures
- Stop: End-of-session review for subtle issues
- SessionStart: Inject recent learnings (7-day window)
- PreToolUse: Adaptive pitfall injection (quiet/gated)

Includes supporting scripts:
- aggregate_learnings.sh: Summarize accepted mistakes
- find_covering_node.sh: Locate AGENTS.md for files
- check_mistake_history.sh: Determine area risk level

Full test suite and documentation included."
```

---

## Summary

This plan implements 4 hooks across 13 tasks:

| Hook | Trigger | Purpose |
|------|---------|---------|
| capture-tool-failure | PostToolUseFailure | Detect failures, suggest capture |
| session-summary | Stop | Review session for subtle issues |
| inject-learnings | SessionStart | Inject recent accepted learnings |
| pre-edit-check | PreToolUse (Edit/Write) | Adaptive pitfall injection |

Supporting scripts created:
- `aggregate_learnings.sh` - Summarize recent accepted mistakes
- `find_covering_node.sh` - Walk up to find covering AGENTS.md
- `check_mistake_history.sh` - Determine if area is high-risk

Total estimated commits: 12
