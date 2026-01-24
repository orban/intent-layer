#!/usr/bin/env bash
# Capture a mistake for Intent Layer improvement
# Usage: capture_mistake.sh [OPTIONS]

set -euo pipefail

show_help() {
    cat << 'EOF'
capture_mistake.sh - Record mistakes for Intent Layer improvement

USAGE:
    capture_mistake.sh [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -d, --dir DIR           Directory where mistake occurred
    -o, --operation TEXT    What you were trying to do
    --from-git              Auto-fill from recent git activity
    --non-interactive       Fail if prompts needed (for scripting)

OUTPUT:
    Creates report in .intent-layer/mistakes/pending/
    Returns path to created report

WORKFLOW:
    1. Run this script after a mistake is discovered
    2. Answer prompts about what happened
    3. Review generated report in pending/
    4. Human reviews and accepts/rejects
    5. If accepted, update AGENTS.md with check or pitfall

EXAMPLES:
    capture_mistake.sh                              # Fully interactive
    capture_mistake.sh --dir src/auth/              # Partial context
    capture_mistake.sh --from-git                   # Git-aware capture

EXIT CODES:
    0    Report created
    1    Error or cancelled
EOF
    exit 0
}

# Defaults
TARGET_DIR=""
OPERATION=""
FROM_GIT=false
NON_INTERACTIVE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -d|--dir)
            TARGET_DIR="$2"
            shift 2
            ;;
        -o|--operation)
            OPERATION="$2"
            shift 2
            ;;
        --from-git)
            FROM_GIT=true
            shift
            ;;
        --non-interactive)
            NON_INTERACTIVE=true
            shift
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            TARGET_DIR="$1"
            shift
            ;;
    esac
done

# Prompt function (respects --non-interactive)
prompt() {
    local var_name="$1"
    local prompt_text="$2"
    local default="${3:-}"

    if [ "$NON_INTERACTIVE" = true ]; then
        if [ -n "$default" ]; then
            eval "$var_name=\"$default\""
        else
            echo "Error: --non-interactive requires all values via flags" >&2
            exit 1
        fi
        return
    fi

    if [ -n "$default" ]; then
        read -r -p "$prompt_text [$default]: " value
        value="${value:-$default}"
    else
        read -r -p "$prompt_text: " value
    fi
    eval "$var_name=\"\$value\""
}

# Select from options
select_option() {
    local var_name="$1"
    local prompt_text="$2"
    shift 2
    local options=("$@")

    if [ "$NON_INTERACTIVE" = true ]; then
        eval "$var_name=\"${options[0]}\""
        return
    fi

    echo "$prompt_text"
    local i=1
    for opt in "${options[@]}"; do
        echo "  $i) $opt"
        ((i++))
    done

    read -r -p "Select [1-${#options[@]}]: " choice
    choice="${choice:-1}"

    if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#options[@]}" ]; then
        eval "$var_name=\"\${options[$((choice-1))]}\""
    else
        eval "$var_name=\"${options[0]}\""
    fi
}

# Auto-fill from git if requested
if [ "$FROM_GIT" = true ]; then
    # Get most recently changed directory
    if [ -z "$TARGET_DIR" ]; then
        recent_file=$(git diff --name-only HEAD~1 2>/dev/null | head -1 || true)
        if [ -n "$recent_file" ]; then
            TARGET_DIR=$(dirname "$recent_file")
            echo "Auto-detected directory from git: $TARGET_DIR"
        fi
    fi

    # Get recent commit message as operation hint
    if [ -z "$OPERATION" ]; then
        recent_msg=$(git log -1 --pretty=%s 2>/dev/null || true)
        if [ -n "$recent_msg" ]; then
            echo "Recent commit: $recent_msg"
        fi
    fi
fi

# Gather information
echo ""
echo "=== Capture Mistake for Intent Layer ==="
echo ""

# Directory
if [ -z "$TARGET_DIR" ]; then
    prompt TARGET_DIR "Directory where mistake occurred" "."
fi

# Validate directory
if [ ! -d "$TARGET_DIR" ]; then
    echo "Warning: Directory does not exist: $TARGET_DIR" >&2
fi

# Operation
if [ -z "$OPERATION" ]; then
    prompt OPERATION "What were you trying to do?"
fi

# What happened
prompt WHAT_HAPPENED "What went wrong?"

# How discovered
select_option DISCOVERY "How was it discovered?" \
    "Tests failed" \
    "User corrected" \
    "Agent self-caught" \
    "Incident/production issue"

# Root cause
prompt ROOT_CAUSE "Why did it happen? (What knowledge was missing?)"

# Check for existing AGENTS.md
EXISTING_NODE="None"
for check_path in "$TARGET_DIR/AGENTS.md" "$TARGET_DIR/CLAUDE.md"; do
    if [ -f "$check_path" ]; then
        EXISTING_NODE="$check_path"
        break
    fi
done

echo ""
echo "Existing Intent Layer node: $EXISTING_NODE"

# Missing content
prompt MISSING_CONTENT "What was missing from the Intent Layer?"

# Suggested check
echo ""
echo "Suggested fix (press Enter to skip, or describe the check):"
prompt SUGGESTED_CHECK "Check: Before [operation] → [verification]" ""

# Generate report
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PART=$(date +"%Y-%m-%d")
REPORT_ID="MISTAKE-$DATE_PART-$(printf '%03d' $((RANDOM % 1000)))"

# Create directory structure
REPORT_DIR=".intent-layer/mistakes/pending"
mkdir -p "$REPORT_DIR"

REPORT_FILE="$REPORT_DIR/$REPORT_ID.md"

# Map discovery to checkboxes
case "$DISCOVERY" in
    "Tests failed")
        DISC_TESTS="x"; DISC_USER=" "; DISC_AGENT=" "; DISC_INCIDENT=" " ;;
    "User corrected")
        DISC_TESTS=" "; DISC_USER="x"; DISC_AGENT=" "; DISC_INCIDENT=" " ;;
    "Agent self-caught")
        DISC_TESTS=" "; DISC_USER=" "; DISC_AGENT="x"; DISC_INCIDENT=" " ;;
    "Incident/production issue")
        DISC_TESTS=" "; DISC_USER=" "; DISC_AGENT=" "; DISC_INCIDENT="x" ;;
    *)
        DISC_TESTS=" "; DISC_USER=" "; DISC_AGENT=" "; DISC_INCIDENT=" " ;;
esac

# Generate suggested fix section
SUGGESTED_FIX=""
if [ -n "$SUGGESTED_CHECK" ]; then
    SUGGESTED_FIX="**As Pre-flight Check**:
\`\`\`markdown
### [Operation Name]
Before [triggering action]:
- [ ] $SUGGESTED_CHECK

If unchecked → [ask/fix first/stop and escalate].
\`\`\`"
else
    SUGGESTED_FIX="**As Pre-flight Check**:
\`\`\`markdown
### [Operation Name]
Before [triggering action]:
- [ ] [Verifiable check]

If unchecked → [ask/fix first/stop and escalate].
\`\`\`

**As Pitfall** (if check not appropriate):
\`\`\`markdown
- [Awareness-only item]
\`\`\`"
fi

# Write report
cat > "$REPORT_FILE" << EOF
## Mistake Report

**ID**: $REPORT_ID
**Timestamp**: $TIMESTAMP
**Directory**: $TARGET_DIR
**Operation**: $OPERATION

### What Happened
$WHAT_HAPPENED

### How Discovered
- [$DISC_TESTS] Tests failed
- [$DISC_USER] User corrected
- [$DISC_AGENT] Agent self-caught
- [$DISC_INCIDENT] Incident/production issue

### Root Cause
$ROOT_CAUSE

### Intent Layer Gap
- **Existing node**: $EXISTING_NODE
- **Missing content**: $MISSING_CONTENT

### Suggested Fix
$SUGGESTED_FIX

### Disposition
<!-- Filled during review -->
- [ ] Check added to AGENTS.md
- [ ] Pitfall added to AGENTS.md
- [ ] Rejected (reason: _______)
- [ ] Deferred (reason: _______)
EOF

echo ""
echo "=== Report Created ==="
echo ""
echo "Report saved to: $REPORT_FILE"
echo ""
echo "Next steps:"
echo "  1. Review the report: cat $REPORT_FILE"
echo "  2. Refine the suggested fix if needed"
echo "  3. Have a human review and accept/reject"
echo "  4. If accepted, update the AGENTS.md with the check or pitfall"
echo ""
