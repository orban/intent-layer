#!/usr/bin/env bash
# Capture a learning for Intent Layer improvement
# Usage: capture_mistake.sh [OPTIONS]
# Note: Name kept for backwards compatibility - captures all learning types

set -euo pipefail

show_help() {
    cat << 'EOF'
capture_mistake.sh - Record learnings for Intent Layer improvement

USAGE:
    capture_mistake.sh [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -d, --dir DIR           Directory where learning applies
    -o, --operation TEXT    What you were doing
    -t, --type TYPE         Learning type: pitfall, check, pattern, insight
    -w, --what TEXT         What happened / what was learned
    -c, --cause TEXT        Root cause or why this matters
    --from-git              Auto-fill from recent git activity
    --non-interactive       Fail if prompts needed (for scripting)
    --agent-id ID           Identifier for the reporting agent

LEARNING TYPES:
    pitfall    Something that went wrong / gotcha to avoid
    check      Pre-action verification to add
    pattern    Better approach discovered / recommended practice
    insight    Important context or background knowledge

OUTPUT:
    Creates report in .intent-layer/mistakes/pending/
    Returns path to created report

WORKFLOW:
    1. Run this script when you discover something worth documenting
    2. Answer prompts about what was learned
    3. Review generated report in pending/
    4. Human reviews and accepts/rejects
    5. If accepted, integrate into appropriate AGENTS.md section

EXAMPLES:
    capture_mistake.sh                                    # Fully interactive
    capture_mistake.sh --type pattern --dir src/api/     # Capture a pattern
    capture_mistake.sh --type check -o "database migration"
    capture_mistake.sh --from-git                        # Git-aware capture

EXIT CODES:
    0    Report created
    1    Error or cancelled
EOF
    exit 0
}

# Defaults
TARGET_DIR=""
OPERATION=""
LEARNING_TYPE=""
WHAT_HAPPENED=""
ROOT_CAUSE=""
FROM_GIT=false
NON_INTERACTIVE=false
AGENT_ID=""

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
        -t|--type)
            LEARNING_TYPE="$2"
            shift 2
            ;;
        -w|--what)
            WHAT_HAPPENED="$2"
            shift 2
            ;;
        -c|--cause)
            ROOT_CAUSE="$2"
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
        --agent-id)
            AGENT_ID="$2"
            shift 2
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
echo "=== Capture Learning for Intent Layer ==="
echo ""

# Learning type
if [ -z "$LEARNING_TYPE" ]; then
    select_option LEARNING_TYPE "What type of learning is this?" \
        "pitfall" \
        "check" \
        "pattern" \
        "insight"
fi

# Validate learning type
case "$LEARNING_TYPE" in
    pitfall|check|pattern|insight) ;;
    *)
        if [ "$NON_INTERACTIVE" = true ]; then
            echo "Error: Invalid learning type '$LEARNING_TYPE'. Must be: pitfall, check, pattern, insight" >&2
            exit 1
        fi
        echo "Warning: Unknown learning type '$LEARNING_TYPE', defaulting to 'pitfall'" >&2
        LEARNING_TYPE="pitfall"
        ;;
esac

# Directory
if [ -z "$TARGET_DIR" ]; then
    prompt TARGET_DIR "Directory where this applies" "."
fi

# Validate directory
if [ ! -d "$TARGET_DIR" ]; then
    echo "Warning: Directory does not exist: $TARGET_DIR" >&2
fi

# Operation context
if [ -z "$OPERATION" ]; then
    case "$LEARNING_TYPE" in
        pitfall) prompt OPERATION "What were you trying to do?" ;;
        check)   prompt OPERATION "What action needs this check?" ;;
        pattern) prompt OPERATION "What task does this pattern apply to?" ;;
        insight) prompt OPERATION "What were you working on?" ;;
    esac
fi

# What happened / was learned
if [ -z "$WHAT_HAPPENED" ]; then
    case "$LEARNING_TYPE" in
        pitfall) prompt WHAT_HAPPENED "What went wrong?" ;;
        check)   prompt WHAT_HAPPENED "What verification is needed?" ;;
        pattern) prompt WHAT_HAPPENED "What's the better approach?" ;;
        insight) prompt WHAT_HAPPENED "What did you learn?" ;;
    esac
fi

# How discovered
select_option DISCOVERY "How was this discovered?" \
    "Agent self-caught" \
    "User corrected" \
    "Tests failed" \
    "Code review" \
    "Experimentation"

# Root cause / why it matters
if [ -z "$ROOT_CAUSE" ]; then
    case "$LEARNING_TYPE" in
        pitfall) prompt ROOT_CAUSE "Why did it happen? (What knowledge was missing?)" ;;
        check)   prompt ROOT_CAUSE "Why is this check important?" ;;
        pattern) prompt ROOT_CAUSE "Why is this approach better?" ;;
        insight) prompt ROOT_CAUSE "Why is this important to know?" ;;
    esac
fi

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
if [ "$NON_INTERACTIVE" = true ]; then
    MISSING_CONTENT=""
    SUGGESTED_CHECK=""
else
    prompt MISSING_CONTENT "What was missing from the Intent Layer?"
    echo ""
    echo "Suggested fix (press Enter to skip, or describe the check):"
    prompt SUGGESTED_CHECK "Check: Before [operation] → [verification]" ""
fi

# Generate report
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PART=$(date +"%Y-%m-%d")

# Use type-based prefix for report ID
TYPE_PREFIX=$(echo "$LEARNING_TYPE" | tr '[:lower:]' '[:upper:]')
REPORT_ID="$TYPE_PREFIX-$DATE_PART-$(printf '%06d' $((RANDOM % 1000000)))-$$"

# Create directory structure
REPORT_DIR=".intent-layer/mistakes/pending"
mkdir -p "$REPORT_DIR"

REPORT_FILE="$REPORT_DIR/$REPORT_ID.md"

# Map discovery to checkboxes
DISC_AGENT=" "; DISC_USER=" "; DISC_TESTS=" "; DISC_REVIEW=" "; DISC_EXPERIMENT=" "
case "$DISCOVERY" in
    "Agent self-caught")  DISC_AGENT="x" ;;
    "User corrected")     DISC_USER="x" ;;
    "Tests failed")       DISC_TESTS="x" ;;
    "Code review")        DISC_REVIEW="x" ;;
    "Experimentation")    DISC_EXPERIMENT="x" ;;
esac

# Generate type-specific sections
SECTION_TITLE=""
SECTION_CONTENT=""
case "$LEARNING_TYPE" in
    pitfall)
        SECTION_TITLE="What Went Wrong"
        SUGGESTED_SECTION="### Suggested Pitfall Entry
\`\`\`markdown
### [Short title]

$WHAT_HAPPENED

_Why_: $ROOT_CAUSE
\`\`\`"
        ;;
    check)
        SECTION_TITLE="Check Needed"
        SUGGESTED_SECTION="### Suggested Check Entry
\`\`\`markdown
### Before $OPERATION
- [ ] $WHAT_HAPPENED

If unchecked → [action to take]
\`\`\`"
        ;;
    pattern)
        SECTION_TITLE="Better Approach"
        SUGGESTED_SECTION="### Suggested Pattern Entry
\`\`\`markdown
### $OPERATION

**Preferred approach**: $WHAT_HAPPENED

_Why_: $ROOT_CAUSE
\`\`\`"
        ;;
    insight)
        SECTION_TITLE="Key Insight"
        SUGGESTED_SECTION="### Suggested Context Entry
\`\`\`markdown
$WHAT_HAPPENED

_Discovered_: $ROOT_CAUSE
\`\`\`"
        ;;
esac

# Write report
AGENT_LINE=""
[[ -n "$AGENT_ID" ]] && AGENT_LINE=$'\n'"**Agent**: $AGENT_ID"

cat > "$REPORT_FILE" << EOF
## Learning Report

**ID**: $REPORT_ID
**Type**: $LEARNING_TYPE
**Timestamp**: $TIMESTAMP
**Directory**: $TARGET_DIR
**Operation**: $OPERATION${AGENT_LINE}

### $SECTION_TITLE
$WHAT_HAPPENED

### How Discovered
- [$DISC_AGENT] Agent self-caught
- [$DISC_USER] User corrected
- [$DISC_TESTS] Tests failed
- [$DISC_REVIEW] Code review
- [$DISC_EXPERIMENT] Experimentation

### Why This Matters
$ROOT_CAUSE

### Intent Layer Gap
- **Existing node**: $EXISTING_NODE
- **Missing content**: $MISSING_CONTENT

$SUGGESTED_SECTION

### Disposition
<!-- Filled during review -->
- [ ] Added to AGENTS.md (section: ________)
- [ ] Rejected (reason: _______)
- [ ] Deferred (reason: _______)
EOF

echo ""
echo "=== Learning Report Created ==="
echo ""
echo "Type: $LEARNING_TYPE"
echo "Report saved to: $REPORT_FILE"
echo ""
echo "Next steps:"
echo "  1. Review the report: cat $REPORT_FILE"
echo "  2. Refine the suggested entry if needed"
echo "  3. Review and accept/reject"
echo "  4. If accepted, integrate into AGENTS.md using:"
echo "     ${CLAUDE_PLUGIN_ROOT:-\$(dirname \$(dirname \$0))}/lib/integrate_pitfall.sh $REPORT_FILE"
echo ""
