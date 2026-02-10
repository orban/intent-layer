#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
TEST_DIR=""
PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

cleanup() {
    [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}
trap cleanup EXIT

echo "=== Feedback Loop Tests ==="
echo ""

# ============================================================
# Fixture: project with .intent-layer/ and AGENTS.md
# ============================================================
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# Root node
cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

## Contracts

- All API calls must be authenticated
EOF

# Child node with pitfalls
mkdir -p "$TEST_DIR/src/api"
cat > "$TEST_DIR/src/api/AGENTS.md" << 'EOF'
# API Module

## Pitfalls

### validate() silently passes on empty input

Always check input length before calling validate().
EOF

touch "$TEST_DIR/src/api/handlers.ts"

# Create .intent-layer directory (required for injection log)
mkdir -p "$TEST_DIR/.intent-layer"

# ---- Test 1: Injection log created ----
echo "Test 1: Injection log created by pre-edit-check.sh"

# Mock JSON input for an Edit tool call
MOCK_INPUT='{"tool_name":"Edit","tool_input":{"file_path":"'"$TEST_DIR"'/src/api/handlers.ts","old_string":"foo","new_string":"bar"}}'

echo "$MOCK_INPUT" | "$PLUGIN_DIR/scripts/pre-edit-check.sh" >/dev/null 2>&1 || true

LOG_FILE="$TEST_DIR/.intent-layer/hooks/injections.log"
if [[ -f "$LOG_FILE" ]]; then
    if grep -q "src/api/handlers.ts" "$LOG_FILE"; then
        pass "Injection log created with file path"
    else
        fail "Injection log exists but missing file path"
    fi
else
    fail "No injection log file created at $LOG_FILE"
fi

# ---- Test 2: Log line format ----
echo "Test 2: Log line matches expected format"

if [[ -f "$LOG_FILE" ]]; then
    LINE=$(tail -1 "$LOG_FILE")
    # Expected format: YYYY-MM-DDTHH:MM:SSZ /path/to/file /path/to/node Sections
    if echo "$LINE" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z .+ .+ Pitfalls'; then
        pass "Log line format: timestamp, file, node, sections"
    else
        fail "Unexpected log format: $LINE"
    fi
else
    fail "No log file to check format"
fi

# ---- Test 3: No log without .intent-layer ----
echo "Test 3: No injection log created without .intent-layer directory"

# Create a clean project without .intent-layer
CLEAN_DIR=$(mktemp -d)
export CLAUDE_PROJECT_DIR="$CLEAN_DIR"

cat > "$CLEAN_DIR/CLAUDE.md" << 'EOF'
# Clean Project

## Pitfalls

### Some pitfall

Details here.
EOF

mkdir -p "$CLEAN_DIR/src"
touch "$CLEAN_DIR/src/file.ts"

MOCK_INPUT2='{"tool_name":"Edit","tool_input":{"file_path":"'"$CLEAN_DIR"'/src/file.ts","old_string":"foo","new_string":"bar"}}'

echo "$MOCK_INPUT2" | "$PLUGIN_DIR/scripts/pre-edit-check.sh" >/dev/null 2>&1 || true

if [[ ! -d "$CLEAN_DIR/.intent-layer" ]]; then
    pass "No .intent-layer directory created on clean project"
else
    fail ".intent-layer directory was created unexpectedly"
fi

rm -rf "$CLEAN_DIR"

# Restore project dir
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# ---- Test 4: Failure correlation ----
echo "Test 4: Failure-injection correlation in skeleton report"

# Write a mock injection log entry
mkdir -p "$TEST_DIR/.intent-layer/hooks"
echo "2026-02-09T10:00:00Z $TEST_DIR/src/api/handlers.ts $TEST_DIR/src/api/AGENTS.md Pitfalls" \
    > "$TEST_DIR/.intent-layer/hooks/injections.log"

# Mock a tool failure on the same file
FAILURE_INPUT='{"tool_name":"Edit","tool_input":{"file_path":"'"$TEST_DIR"'/src/api/handlers.ts","old_string":"nonexistent","new_string":"replacement"}}'

echo "$FAILURE_INPUT" | "$PLUGIN_DIR/scripts/capture-tool-failure.sh" >/dev/null 2>&1 || true

# Check if any skeleton report mentions injection history
FOUND_CORRELATION=false
if [[ -d "$TEST_DIR/.intent-layer/mistakes/pending" ]]; then
    for report in "$TEST_DIR/.intent-layer/mistakes/pending"/SKELETON-*.md; do
        [[ -f "$report" ]] || continue
        if grep -q "Injection history" "$report"; then
            FOUND_CORRELATION=true
            break
        fi
    done
fi

if $FOUND_CORRELATION; then
    pass "Skeleton report contains injection history correlation"
else
    fail "No injection history found in skeleton reports"
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[[ "$FAILED" -gt 0 ]] && exit 1
echo "All tests passed!"
