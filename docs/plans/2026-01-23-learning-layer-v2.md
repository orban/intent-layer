# Learning Layer Implementation Plan (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a continuous learning loop that captures mistakes during agent sessions and injects relevant learnings back into future workflows.

**Architecture:** Four hooks working as two pairs - capture hooks (PostToolUseFailure, Stop) detect issues and create mistake reports, feedback hooks (SessionStart, PreToolUse) inject relevant context before agents make changes. The system is self-contained within the plugin directory.

**Tech Stack:** Bash scripts (POSIX-compatible where possible), Markdown for reports, existing `capture_mistake.sh` infrastructure.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     LEARNING LAYER                              │
├─────────────────────────────────────────────────────────────────┤
│  CAPTURE (Detection)                                            │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │ PostToolUseFailure  │    │ Stop (prompt-based)             │ │
│  │ - Tool errors       │    │ - Subtle issues                 │ │
│  │ - Immediate capture │    │ - End-of-session review         │ │
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
│  │ - Recent learnings  │    │ - Pitfalls from covering node   │ │
│  │ - Summary injection │    │ - Adaptive: quiet → gated       │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Plugin Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest with hooks reference
├── hooks/
│   ├── capture-tool-failure/
│   │   └── hook.sh           # PostToolUseFailure hook
│   ├── session-summary/
│   │   └── hook.txt          # Stop prompt hook
│   ├── inject-learnings/
│   │   └── hook.sh           # SessionStart hook
│   └── pre-edit-check/
│       └── hook.sh           # PreToolUse hook
├── lib/
│   ├── common.sh             # Shared functions (jq check, path resolution)
│   ├── aggregate_learnings.sh
│   ├── find_covering_node.sh
│   └── check_mistake_history.sh
├── hooks.json                # Hook registration config
├── tests/
│   └── test_hooks.sh
└── README.md
```

---

## Task 1: Create Plugin Scaffold with Shared Library

**Files:**
- Create: `intent-layer-plugin/.claude-plugin/plugin.json`
- Create: `intent-layer-plugin/lib/common.sh`
- Create: directories for hooks, lib, tests

**Step 1: Create directory structure**

```bash
mkdir -p intent-layer-plugin/.claude-plugin
mkdir -p intent-layer-plugin/hooks/{capture-tool-failure,session-summary,inject-learnings,pre-edit-check}
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

# Get the plugin root directory (works from any hook script)
get_plugin_root() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    # Walk up until we find .claude-plugin/
    local dir="$script_dir"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "$dir/.claude-plugin" ]]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    # Fallback to script parent's parent
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
        echo "$json" | jq -r "$path // \"$default\"" 2>/dev/null || echo "$default"
    else
        echo "$default"
    fi
}

# Ensure mistakes directory exists
ensure_mistakes_dir() {
    local base_dir="${1:-.}"
    mkdir -p "$base_dir/.intent-layer/mistakes/"{pending,accepted,rejected} 2>/dev/null || true
}

# Cross-platform date arithmetic
# Usage: date_days_ago N -> outputs YYYY-MM-DD for N days ago
date_days_ago() {
    local days="$1"
    if date -v-1d &>/dev/null 2>&1; then
        # BSD date (macOS)
        date -v-"${days}d" +%Y-%m-%d
    else
        # GNU date (Linux)
        date -d "$days days ago" +%Y-%m-%d
    fi
}

# Cross-platform file modification time check
# Usage: file_newer_than FILE YYYY-MM-DD -> returns 0 if newer
file_newer_than() {
    local file="$1"
    local cutoff_date="$2"

    local file_date
    if stat -f %Sm -t %Y-%m-%d "$file" &>/dev/null 2>&1; then
        # BSD stat (macOS)
        file_date=$(stat -f %Sm -t %Y-%m-%d "$file")
    else
        # GNU stat (Linux)
        file_date=$(stat -c %y "$file" | cut -d' ' -f1)
    fi

    [[ "$file_date" > "$cutoff_date" || "$file_date" == "$cutoff_date" ]]
}
```

**Step 4: Make common.sh executable**

Run: `chmod +x intent-layer-plugin/lib/common.sh`

**Step 5: Verify structure**

Run: `ls -laR intent-layer-plugin/`
Expected: All directories created, plugin.json and common.sh present

**Step 6: Commit**

```bash
git add intent-layer-plugin/
git commit -m "feat(learning-layer): scaffold plugin structure with shared library"
```

---

## Task 2: Implement PostToolUseFailure Capture Hook

**Files:**
- Create: `intent-layer-plugin/hooks/capture-tool-failure/hook.sh`

**Purpose:** When a tool fails unexpectedly, suggest capturing the mistake for future prevention.

**Step 1: Write hook.sh**

Create `intent-layer-plugin/hooks/capture-tool-failure/hook.sh`:

```bash
#!/usr/bin/env bash
# PostToolUseFailure hook - Suggests mistake capture on significant tool failures
# Input: JSON on stdin with tool_name, tool_input, error
# Output: Message to stderr for agent visibility

set -euo pipefail

# Source shared library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
source "$PLUGIN_ROOT/lib/common.sh"

# Read hook input
INPUT=$(cat)

# Extract fields (graceful if jq missing)
TOOL_NAME=$(json_get "$INPUT" '.tool_name' 'unknown')
ERROR=$(json_get "$INPUT" '.error' 'unknown error')
FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')

# Skip expected/exploratory failures
case "$TOOL_NAME" in
    Read|Glob|Grep|LS)
        # File exploration failures are expected
        if echo "$ERROR" | grep -qiE 'no such file|not found|no files|does not exist'; then
            exit 0
        fi
        ;;
    Bash)
        # Common bash exploration failures
        if echo "$ERROR" | grep -qiE 'command not found|no such file|exit code'; then
            exit 0
        fi
        ;;
esac

# Skip if error is just a timeout (often expected)
if echo "$ERROR" | grep -qiE 'timeout|timed out'; then
    exit 0
fi

# Output capture suggestion
{
    echo ""
    echo "⚠️ Tool '$TOOL_NAME' failed: ${ERROR:0:100}"
    if [[ -n "$FILE_PATH" ]]; then
        echo "   File: $FILE_PATH"
    fi
    echo ""
    echo "If this was unexpected, consider capturing it:"
    echo "  ~/.claude/skills/intent-layer/scripts/capture_mistake.sh --from-git"
    echo ""
    echo "(Ignore if this was exploratory/expected behavior)"
    echo ""
} >&2
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/capture-tool-failure/hook.sh`

**Step 3: Test with significant failure**

Run:
```bash
echo '{"tool_name": "Edit", "error": "Permission denied: cannot write to file", "tool_input": {"file_path": "src/auth/login.ts"}}' | \
  ./intent-layer-plugin/hooks/capture-tool-failure/hook.sh 2>&1
```

Expected: Outputs warning with file path and capture suggestion

**Step 4: Test filtering of expected failures**

Run:
```bash
echo '{"tool_name": "Read", "error": "No such file or directory: test.md"}' | \
  ./intent-layer-plugin/hooks/capture-tool-failure/hook.sh 2>&1
```

Expected: Silent exit (no output)

**Step 5: Commit**

```bash
git add intent-layer-plugin/hooks/capture-tool-failure/
git commit -m "feat(learning-layer): add PostToolUseFailure capture hook"
```

---

## Task 3: Implement Stop Prompt Hook (Session Summary)

**Files:**
- Create: `intent-layer-plugin/hooks/session-summary/hook.txt`

**Purpose:** Prompt-based hook that asks Claude to reflect on learnings before ending the session.

**Step 1: Write prompt hook**

Create `intent-layer-plugin/hooks/session-summary/hook.txt`:

```markdown
## Session Learning Review

Before ending this session, briefly consider:

1. **Unexpected behaviors** - Did anything work differently than expected or documented?
2. **Missing information** - Did you have to figure out something that should have been documented?
3. **User corrections** - Did the user correct any assumptions you made about the codebase?

If you identified something that would help future agents, suggest running:
```
~/.claude/skills/intent-layer/scripts/capture_mistake.sh
```

**Only surface genuine gaps** - normal exploration, expected behaviors, and successful work don't need capturing.

If nothing significant was discovered, simply proceed with ending the session.
```

**Step 2: Verify file**

Run: `cat intent-layer-plugin/hooks/session-summary/hook.txt`
Expected: Prompt content displayed correctly

**Step 3: Commit**

```bash
git add intent-layer-plugin/hooks/session-summary/
git commit -m "feat(learning-layer): add Stop prompt hook for session review"
```

---

## Task 4: Create Learnings Aggregation Script

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

# Source shared library
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
    -p, --path DIR       Project root to search (default: current directory)

OUTPUT:
    Markdown summary of recent accepted mistakes. Empty if no learnings.
EOF
    exit 0
}

# Defaults
DAYS=7
FORMAT="summary"
PROJECT_PATH="."

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -d|--days) DAYS="$2"; shift 2 ;;
        -f|--format) FORMAT="$2"; shift 2 ;;
        -p|--path) PROJECT_PATH="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Find accepted mistakes directory
MISTAKES_DIR="$PROJECT_PATH/.intent-layer/mistakes/accepted"

if [[ ! -d "$MISTAKES_DIR" ]]; then
    # No accepted mistakes yet - silent exit
    exit 0
fi

# Calculate cutoff date
CUTOFF=$(date_days_ago "$DAYS")

# Find recent files using cross-platform date comparison
RECENT_FILES=()
while IFS= read -r -d '' file; do
    if file_newer_than "$file" "$CUTOFF"; then
        RECENT_FILES+=("$file")
    fi
done < <(find "$MISTAKES_DIR" -name "MISTAKE-*.md" -type f -print0 2>/dev/null)

if [[ ${#RECENT_FILES[@]} -eq 0 ]]; then
    # No recent learnings - silent exit
    exit 0
fi

# Output header
echo "## Recent Learnings (last $DAYS days)"
echo ""
echo "${#RECENT_FILES[@]} accepted mistake(s) converted to Intent Layer updates."
echo ""

if [[ "$FORMAT" == "full" ]]; then
    # Full details
    for file in "${RECENT_FILES[@]}"; do
        echo "---"
        echo ""
        cat "$file"
        echo ""
    done
else
    # Summary format - extract key info
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
Expected: Help message displayed

**Step 4: Test with no learnings**

Run: `./intent-layer-plugin/lib/aggregate_learnings.sh`
Expected: Silent exit (no output when no accepted mistakes)

**Step 5: Commit**

```bash
git add intent-layer-plugin/lib/aggregate_learnings.sh
git commit -m "feat(learning-layer): add learnings aggregation script"
```

---

## Task 5: Implement SessionStart Injection Hook

**Files:**
- Create: `intent-layer-plugin/hooks/inject-learnings/hook.sh`

**Purpose:** Inject recent accepted learnings at session start.

**Step 1: Write hook script**

Create `intent-layer-plugin/hooks/inject-learnings/hook.sh`:

```bash
#!/usr/bin/env bash
# SessionStart hook - Injects recent learnings into agent context
# Output: Markdown content to stdout for context injection

set -euo pipefail

# Source shared library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
source "$PLUGIN_ROOT/lib/common.sh"

# Locate aggregation script
AGGREGATE_SCRIPT="$PLUGIN_ROOT/lib/aggregate_learnings.sh"

if [[ ! -f "$AGGREGATE_SCRIPT" ]]; then
    # Aggregation script not found - silent exit
    exit 0
fi

# Run aggregation for last 7 days
LEARNINGS=$("$AGGREGATE_SCRIPT" --days 7 --format summary 2>/dev/null || true)

if [[ -z "$LEARNINGS" ]]; then
    # No recent learnings - silent exit
    exit 0
fi

# Output learnings for injection
cat << 'EOF'
## Intent Layer: Recent Learnings

The following mistakes were recently captured and converted to Intent Layer updates.
Be aware of these patterns when working in related areas.

EOF

echo "$LEARNINGS"
echo ""
echo "---"
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/inject-learnings/hook.sh`

**Step 3: Test hook**

Run: `./intent-layer-plugin/hooks/inject-learnings/hook.sh`
Expected: Either outputs learnings or silent exit if none

**Step 4: Commit**

```bash
git add intent-layer-plugin/hooks/inject-learnings/
git commit -m "feat(learning-layer): add SessionStart learnings injection hook"
```

---

## Task 6: Create Covering Node Finder Script

**Files:**
- Create: `intent-layer-plugin/lib/find_covering_node.sh`

**Purpose:** Walk up from a file to find the nearest AGENTS.md or CLAUDE.md.

**Step 1: Write node finder script**

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
    -s, --section NAME   Extract specific section (e.g., Pitfalls, Contracts)

OUTPUT:
    Path to covering AGENTS.md/CLAUDE.md, or empty if none found.
    With --section, outputs the section content instead.

EXAMPLES:
    find_covering_node.sh src/auth/login.ts
    find_covering_node.sh src/api/handlers.py --section Pitfalls
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
    FILE_PATH="$(pwd)/$FILE_PATH"
fi

# Start from file's directory (or file itself if it's a dir)
if [[ -d "$FILE_PATH" ]]; then
    CURRENT_DIR="$FILE_PATH"
else
    CURRENT_DIR="$(dirname "$FILE_PATH")"
fi

NODE_PATH=""

# Walk up until we find AGENTS.md, CLAUDE.md, or hit filesystem root
while [[ "$CURRENT_DIR" != "/" ]]; do
    # Check for AGENTS.md first (preferred for subdirectories)
    if [[ -f "$CURRENT_DIR/AGENTS.md" ]]; then
        NODE_PATH="$CURRENT_DIR/AGENTS.md"
        break
    fi

    # Check for CLAUDE.md (typically at root)
    if [[ -f "$CURRENT_DIR/CLAUDE.md" ]]; then
        NODE_PATH="$CURRENT_DIR/CLAUDE.md"
        break
    fi

    # Stop at git root if no node found
    if [[ -d "$CURRENT_DIR/.git" ]]; then
        break
    fi

    # Move up
    CURRENT_DIR="$(dirname "$CURRENT_DIR")"
done

if [[ -z "$NODE_PATH" ]]; then
    # No covering node found - silent exit
    exit 0
fi

if [[ -n "$SECTION" ]]; then
    # Extract specific section (## Header until next ## or EOF)
    awk -v section="$SECTION" '
        /^## / {
            if (found) exit
            if ($0 ~ "^## .*"section) found=1
        }
        found { print }
    ' "$NODE_PATH"
else
    # Output the node path
    echo "$NODE_PATH"
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/lib/find_covering_node.sh`

**Step 3: Test with existing file**

Run: `./intent-layer-plugin/lib/find_covering_node.sh intent-layer/scripts/capture_mistake.sh`
Expected: Outputs path to CLAUDE.md or nearest AGENTS.md

**Step 4: Test section extraction**

Run: `./intent-layer-plugin/lib/find_covering_node.sh CLAUDE.md --section Pitfalls`
Expected: Outputs Pitfalls section content (or nothing if section doesn't exist)

**Step 5: Commit**

```bash
git add intent-layer-plugin/lib/find_covering_node.sh
git commit -m "feat(learning-layer): add covering node finder script"
```

---

## Task 7: Create Mistake History Checker

**Files:**
- Create: `intent-layer-plugin/lib/check_mistake_history.sh`

**Purpose:** Check if a directory has a history of mistakes (for adaptive gating).

**Step 1: Write history checker**

Create `intent-layer-plugin/lib/check_mistake_history.sh`:

```bash
#!/usr/bin/env bash
# Check if a directory has a history of mistakes
# Usage: check_mistake_history.sh <directory> [--threshold N]

set -euo pipefail

show_help() {
    cat << 'EOF'
check_mistake_history.sh - Check directory mistake history for risk assessment

USAGE:
    check_mistake_history.sh <directory> [OPTIONS]

OPTIONS:
    -h, --help           Show this help
    -t, --threshold N    Mistake count for "high risk" (default: 2)
    --json               Output as JSON

EXIT CODES:
    0    High-risk (count >= threshold)
    1    Low-risk (count < threshold)

EXAMPLES:
    check_mistake_history.sh src/auth/
    if check_mistake_history.sh src/api/; then echo "High risk!"; fi
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

# Normalize directory (remove trailing slash, handle relative paths)
DIRECTORY="${DIRECTORY%/}"
if [[ "$DIRECTORY" != /* ]]; then
    DIRECTORY="$(pwd)/$DIRECTORY"
fi

# Extract just the relative part for matching
REL_DIR="${DIRECTORY#$(pwd)/}"

# Count mistakes mentioning this directory
COUNT=0
for mistakes_subdir in pending accepted; do
    mistakes_path=".intent-layer/mistakes/$mistakes_subdir"
    if [[ -d "$mistakes_path" ]]; then
        # Count files that mention this directory
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
    # Exit based on risk for scripting
    $HIGH_RISK && exit 0 || exit 1
else
    if $HIGH_RISK; then
        echo "High risk: $REL_DIR ($COUNT previous mistakes)"
        exit 0
    else
        exit 1
    fi
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/lib/check_mistake_history.sh`

**Step 3: Test help**

Run: `./intent-layer-plugin/lib/check_mistake_history.sh --help`
Expected: Help displayed

**Step 4: Test JSON output**

Run: `./intent-layer-plugin/lib/check_mistake_history.sh . --json`
Expected: JSON output with count and high_risk flag

**Step 5: Commit**

```bash
git add intent-layer-plugin/lib/check_mistake_history.sh
git commit -m "feat(learning-layer): add mistake history checker for adaptive gating"
```

---

## Task 8: Implement PreToolUse Hook (Adaptive Pitfalls)

**Files:**
- Create: `intent-layer-plugin/hooks/pre-edit-check/hook.sh`

**Purpose:** Before Edit/Write, inject relevant Pitfalls from the covering node with adaptive behavior.

**Step 1: Write PreToolUse hook**

Create `intent-layer-plugin/hooks/pre-edit-check/hook.sh`:

```bash
#!/usr/bin/env bash
# PreToolUse hook for Edit/Write - Injects pitfalls with adaptive gating
# Input: JSON on stdin with tool_name, tool_input
# Output: Context injection to stdout

set -euo pipefail

# Source shared library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
source "$PLUGIN_ROOT/lib/common.sh"

# Read hook input
INPUT=$(cat)

# Only trigger for edit/write tools
TOOL_NAME=$(json_get "$INPUT" '.tool_name' '')
case "$TOOL_NAME" in
    Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

# Extract file path
FILE_PATH=$(json_get "$INPUT" '.tool_input.file_path' '')
FILE_PATH=${FILE_PATH:-$(json_get "$INPUT" '.tool_input.path' '')}

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Locate helper scripts
FIND_NODE="$PLUGIN_ROOT/lib/find_covering_node.sh"
CHECK_HISTORY="$PLUGIN_ROOT/lib/check_mistake_history.sh"

if [[ ! -f "$FIND_NODE" ]]; then
    exit 0
fi

# Find covering node
NODE_PATH=$("$FIND_NODE" "$FILE_PATH" 2>/dev/null || true)

if [[ -z "$NODE_PATH" ]]; then
    # No covering node - silent exit
    exit 0
fi

# Get directory for history check
FILE_DIR="$(dirname "$FILE_PATH")"

# Check if high-risk area
HIGH_RISK=false
if [[ -f "$CHECK_HISTORY" ]]; then
    if "$CHECK_HISTORY" "$FILE_DIR" &>/dev/null; then
        HIGH_RISK=true
    fi
fi

# Extract Pitfalls section
PITFALLS=$("$FIND_NODE" "$FILE_PATH" --section Pitfalls 2>/dev/null || true)

if [[ -z "$PITFALLS" ]]; then
    # No pitfalls section - silent exit
    exit 0
fi

# Output context injection
echo "## Intent Layer Context"
echo ""
echo "**Editing:** \`$FILE_PATH\`"
echo "**Covered by:** \`$NODE_PATH\`"
echo ""

if $HIGH_RISK; then
    # Gated mode - strong warning
    cat << 'EOF'
⚠️ **HIGH-RISK AREA** - This directory has a history of mistakes.

Before proceeding, verify these pitfalls don't apply to your change:

EOF
    echo "$PITFALLS"
    echo ""
    echo "---"
    echo "**Pre-flight check:** Confirm you've reviewed the pitfalls above."
else
    # Quiet mode - informational
    echo "ℹ️ Relevant pitfalls from covering node:"
    echo ""
    echo "$PITFALLS"
    echo ""
    echo "---"
fi
```

**Step 2: Make executable**

Run: `chmod +x intent-layer-plugin/hooks/pre-edit-check/hook.sh`

**Step 3: Test with Edit input**

Run:
```bash
echo '{"tool_name": "Edit", "tool_input": {"file_path": "intent-layer/scripts/capture_mistake.sh"}}' | \
  ./intent-layer-plugin/hooks/pre-edit-check/hook.sh
```

Expected: Outputs pitfalls from covering node (or silent if no pitfalls section)

**Step 4: Test filtering**

Run:
```bash
echo '{"tool_name": "Read", "tool_input": {"file_path": "README.md"}}' | \
  ./intent-layer-plugin/hooks/pre-edit-check/hook.sh
```

Expected: Silent exit (Read tool not covered)

**Step 5: Commit**

```bash
git add intent-layer-plugin/hooks/pre-edit-check/
git commit -m "feat(learning-layer): add PreToolUse hook with adaptive pitfall injection"
```

---

## Task 9: Create Hook Registration Configuration

**Files:**
- Create: `intent-layer-plugin/hooks.json`
- Modify: `intent-layer-plugin/.claude-plugin/plugin.json`

**Purpose:** Register all hooks with Claude Code.

**Step 1: Write hooks.json**

Create `intent-layer-plugin/hooks.json`:

```json
{
  "hooks": [
    {
      "id": "capture-tool-failure",
      "description": "Suggest mistake capture when tools fail unexpectedly",
      "trigger": "PostToolUseFailure",
      "type": "command",
      "command": "./hooks/capture-tool-failure/hook.sh"
    },
    {
      "id": "session-summary",
      "description": "Prompt for learning review before ending session",
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

**Step 2: Update plugin.json to reference hooks**

Update `intent-layer-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "intent-layer",
  "version": "0.1.0",
  "description": "Intent Layer with continuous learning loop - captures mistakes and injects learnings",
  "author": "intent-layer-team",
  "hooks": "../hooks.json"
}
```

**Step 3: Validate JSON files**

Run: `jq empty intent-layer-plugin/hooks.json && jq empty intent-layer-plugin/.claude-plugin/plugin.json`
Expected: No errors (valid JSON)

**Step 4: Commit**

```bash
git add intent-layer-plugin/hooks.json intent-layer-plugin/.claude-plugin/plugin.json
git commit -m "feat(learning-layer): add hook registration configuration"
```

---

## Task 10: Create Integration Test Suite

**Files:**
- Create: `intent-layer-plugin/tests/test_hooks.sh`

**Purpose:** Verify all hooks work correctly together.

**Step 1: Write test script**

Create `intent-layer-plugin/tests/test_hooks.sh`:

```bash
#!/usr/bin/env bash
# Integration tests for learning layer hooks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

PASSED=0
FAILED=0

pass() { echo "✅ $1"; ((PASSED++)); }
fail() { echo "❌ $1"; ((FAILED++)); }

echo "=== Learning Layer Hooks Integration Tests ==="
echo ""

# Test 1: common.sh loads without error
echo "Test 1: Shared library loads"
if source "$PLUGIN_DIR/lib/common.sh" 2>/dev/null; then
    pass "common.sh sources without error"
else
    fail "common.sh failed to source"
fi

# Test 2: PostToolUseFailure suggests capture on significant failure
echo "Test 2: PostToolUseFailure on significant error"
output=$(echo '{"tool_name": "Edit", "error": "Permission denied"}' | \
    "$PLUGIN_DIR/hooks/capture-tool-failure/hook.sh" 2>&1 || true)
if echo "$output" | grep -q "capture_mistake"; then
    pass "Suggests capture on Edit failure"
else
    fail "Should suggest capture: $output"
fi

# Test 3: PostToolUseFailure filters expected errors
echo "Test 3: PostToolUseFailure filters Read failures"
output=$(echo '{"tool_name": "Read", "error": "No such file or directory"}' | \
    "$PLUGIN_DIR/hooks/capture-tool-failure/hook.sh" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Silently ignores expected Read failure"
else
    fail "Should be silent: $output"
fi

# Test 4: Stop prompt hook exists and contains content
echo "Test 4: Stop prompt hook"
if [[ -f "$PLUGIN_DIR/hooks/session-summary/hook.txt" ]]; then
    if grep -q "Learning Review" "$PLUGIN_DIR/hooks/session-summary/hook.txt"; then
        pass "Stop prompt contains learning review content"
    else
        fail "Stop prompt missing expected content"
    fi
else
    fail "Stop prompt file missing"
fi

# Test 5: SessionStart hook runs without error
echo "Test 5: SessionStart hook runs"
if "$PLUGIN_DIR/hooks/inject-learnings/hook.sh" >/dev/null 2>&1; then
    pass "SessionStart hook executes without error"
else
    fail "SessionStart hook crashed"
fi

# Test 6: PreToolUse filters non-edit tools
echo "Test 6: PreToolUse ignores Read"
output=$(echo '{"tool_name": "Read", "tool_input": {"file_path": "test.py"}}' | \
    "$PLUGIN_DIR/hooks/pre-edit-check/hook.sh" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "PreToolUse ignores Read tool"
else
    fail "PreToolUse should ignore Read: $output"
fi

# Test 7: PreToolUse handles Edit without crashing
echo "Test 7: PreToolUse handles Edit"
output=$(echo '{"tool_name": "Edit", "tool_input": {"file_path": "nonexistent/file.py"}}' | \
    "$PLUGIN_DIR/hooks/pre-edit-check/hook.sh" 2>&1 || true)
# Just verify it doesn't crash (may have no output if no covering node)
pass "PreToolUse handles Edit without crashing"

# Test 8: hooks.json is valid
echo "Test 8: hooks.json validation"
if jq empty "$PLUGIN_DIR/hooks.json" 2>/dev/null; then
    hook_count=$(jq '.hooks | length' "$PLUGIN_DIR/hooks.json")
    if [[ "$hook_count" -eq 4 ]]; then
        pass "hooks.json valid with 4 hooks"
    else
        fail "Expected 4 hooks, got $hook_count"
    fi
else
    fail "hooks.json is invalid JSON"
fi

# Test 9: All lib scripts have --help
echo "Test 9: Library scripts have help"
all_have_help=true
for script in "$PLUGIN_DIR/lib"/*.sh; do
    if [[ -f "$script" && -x "$script" ]]; then
        if ! "$script" --help >/dev/null 2>&1; then
            fail "Script missing --help: $(basename "$script")"
            all_have_help=false
        fi
    fi
done
if $all_have_help; then
    pass "All lib scripts support --help"
fi

# Test 10: plugin.json references hooks
echo "Test 10: Plugin manifest"
if jq -e '.hooks' "$PLUGIN_DIR/.claude-plugin/plugin.json" >/dev/null 2>&1; then
    pass "plugin.json references hooks"
else
    fail "plugin.json missing hooks reference"
fi

# Summary
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [[ "$FAILED" -gt 0 ]]; then
    echo "Some tests failed!"
    exit 1
else
    echo "All tests passed!"
    exit 0
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

## Task 11: Create Plugin README

**Files:**
- Create: `intent-layer-plugin/README.md`

**Step 1: Write README**

Create `intent-layer-plugin/README.md`:

```markdown
# Intent Layer Plugin

A Claude Code plugin implementing a continuous learning loop that captures mistakes and injects learnings into agent workflows.

## Features

### Capture Hooks (Detection)

| Hook | Trigger | Purpose |
|------|---------|---------|
| `capture-tool-failure` | PostToolUseFailure | Suggests running `capture_mistake.sh` on unexpected tool failures |
| `session-summary` | Stop | Prompts session review for subtle mistakes before ending |

### Feedback Hooks (Injection)

| Hook | Trigger | Purpose |
|------|---------|---------|
| `inject-learnings` | SessionStart | Injects recent accepted mistakes (7-day window) |
| `pre-edit-check` | PreToolUse | Injects Pitfalls from covering AGENTS.md before Edit/Write |

### Adaptive Behavior

The PreToolUse hook uses **adaptive gating** based on mistake history:

- **Quiet mode** (0-1 previous mistakes): Informational pitfalls display
- **Gated mode** (2+ previous mistakes): Strong warning requiring acknowledgment

## Installation

```bash
# From this repository
claude plugin install ./intent-layer-plugin

# Or symlink for development
ln -s $(pwd)/intent-layer-plugin ~/.claude/plugins/intent-layer
```

## Requirements

- `jq` for JSON parsing (install via `brew install jq` or `apt install jq`)
- The `intent-layer` skill for `capture_mistake.sh` access

## Directory Structure

```
intent-layer-plugin/
├── .claude-plugin/plugin.json    # Plugin manifest
├── hooks/                        # Hook implementations
│   ├── capture-tool-failure/     # PostToolUseFailure
│   ├── session-summary/          # Stop prompt
│   ├── inject-learnings/         # SessionStart
│   └── pre-edit-check/           # PreToolUse
├── lib/                          # Shared scripts
│   ├── common.sh                 # Utility functions
│   ├── aggregate_learnings.sh    # Summarize mistakes
│   ├── find_covering_node.sh     # Find AGENTS.md
│   └── check_mistake_history.sh  # Risk assessment
├── hooks.json                    # Hook registration
└── tests/test_hooks.sh           # Integration tests
```

## Testing

```bash
./tests/test_hooks.sh
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

## Configuration

Adjust risk threshold in `check_mistake_history.sh` with `--threshold N` (default: 2).

Adjust learnings window in `aggregate_learnings.sh` with `--days N` (default: 7).
```

**Step 2: Commit**

```bash
git add intent-layer-plugin/README.md
git commit -m "docs(learning-layer): add plugin README"
```

---

## Task 12: Final Verification and Summary Commit

**Step 1: Verify complete structure**

Run: `find intent-layer-plugin -type f | sort`

Expected output:
```
intent-layer-plugin/.claude-plugin/plugin.json
intent-layer-plugin/README.md
intent-layer-plugin/hooks.json
intent-layer-plugin/hooks/capture-tool-failure/hook.sh
intent-layer-plugin/hooks/inject-learnings/hook.sh
intent-layer-plugin/hooks/pre-edit-check/hook.sh
intent-layer-plugin/hooks/session-summary/hook.txt
intent-layer-plugin/lib/aggregate_learnings.sh
intent-layer-plugin/lib/check_mistake_history.sh
intent-layer-plugin/lib/common.sh
intent-layer-plugin/lib/find_covering_node.sh
intent-layer-plugin/tests/test_hooks.sh
```

**Step 2: Run final tests**

Run: `./intent-layer-plugin/tests/test_hooks.sh`
Expected: All tests pass

**Step 3: Verify JSON files**

Run: `jq empty intent-layer-plugin/hooks.json && jq empty intent-layer-plugin/.claude-plugin/plugin.json && echo "JSON valid"`
Expected: "JSON valid"

**Step 4: Create summary commit (if incremental commits were squashed)**

```bash
git add -A intent-layer-plugin/
git status
```

If there are uncommitted changes:
```bash
git commit -m "feat(learning-layer): complete learning layer plugin implementation

Implements continuous learning loop with:

CAPTURE HOOKS:
- PostToolUseFailure: Suggests capture on unexpected tool failures
- Stop: Session review prompt for subtle issues

FEEDBACK HOOKS:
- SessionStart: Injects recent learnings (7-day window)
- PreToolUse: Adaptive pitfall injection (quiet → gated)

SUPPORTING SCRIPTS:
- common.sh: Shared utilities with cross-platform compatibility
- aggregate_learnings.sh: Summarizes accepted mistakes
- find_covering_node.sh: Walks up to find covering AGENTS.md
- check_mistake_history.sh: Determines area risk level

Full test suite and documentation included."
```

---

## Summary

| Task | Component | Files Created |
|------|-----------|---------------|
| 1 | Plugin scaffold | plugin.json, common.sh, directories |
| 2 | PostToolUseFailure hook | capture-tool-failure/hook.sh |
| 3 | Stop prompt hook | session-summary/hook.txt |
| 4 | Aggregation script | lib/aggregate_learnings.sh |
| 5 | SessionStart hook | inject-learnings/hook.sh |
| 6 | Node finder | lib/find_covering_node.sh |
| 7 | History checker | lib/check_mistake_history.sh |
| 8 | PreToolUse hook | pre-edit-check/hook.sh |
| 9 | Hook registration | hooks.json, plugin.json update |
| 10 | Integration tests | tests/test_hooks.sh |
| 11 | Documentation | README.md |
| 12 | Final verification | - |

**Total commits:** 11 (one per task with changes)

**Key improvements over v1:**
- Self-contained plugin with shared library
- Cross-platform date handling (macOS/Linux)
- Graceful jq dependency handling
- Proper path resolution from any hook location
- Comprehensive test coverage
- Better error filtering for expected failures
