#!/usr/bin/env bash
# Tests for context telemetry (outcome logging + dashboard)
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

echo "=== Context Telemetry Tests ==="
echo ""

# ============================================================
# Fixture: project with .intent-layer/ directory
# ============================================================
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# Create a minimal project
cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

## Pitfalls

### Watch out for nulls

Check for null before dereferencing.
EOF

mkdir -p "$TEST_DIR/src/api"
cat > "$TEST_DIR/src/api/AGENTS.md" << 'EOF'
# API Module

## Pitfalls

### validate() silently passes on empty input

Always check input length before calling validate().
EOF

touch "$TEST_DIR/src/api/handlers.ts"
mkdir -p "$TEST_DIR/.intent-layer/hooks"

# ---- Test 1: post-edit-check.sh writes to outcomes.log ----
echo "Test 1: post-edit-check.sh writes success to outcomes.log"

"$PLUGIN_DIR/scripts/post-edit-check.sh" \
    "{\"file_path\": \"$TEST_DIR/src/api/handlers.ts\", \"old_string\": \"foo\", \"new_string\": \"bar\"}" \
    >/dev/null 2>&1 || true

OUTCOMES_LOG="$TEST_DIR/.intent-layer/hooks/outcomes.log"
if [[ -f "$OUTCOMES_LOG" ]]; then
    LINE=$(tail -1 "$OUTCOMES_LOG")
    if echo "$LINE" | grep -q "success" && echo "$LINE" | grep -q "handlers.ts"; then
        pass "post-edit-check.sh logs success outcome"
    else
        fail "Outcome line unexpected: $LINE"
    fi
else
    fail "No outcomes.log created"
fi

# ---- Test 2: outcome log format (4 TSV fields) ----
echo "Test 2: Outcome log line format"

if [[ -f "$OUTCOMES_LOG" ]]; then
    LINE=$(tail -1 "$OUTCOMES_LOG")
    FIELD_COUNT=$(echo "$LINE" | awk -F'\t' '{print NF}')
    TOOL_FIELD=$(echo "$LINE" | awk -F'\t' '{print $2}')
    RESULT_FIELD=$(echo "$LINE" | awk -F'\t' '{print $3}')
    if [[ "$FIELD_COUNT" -eq 4 && "$TOOL_FIELD" == "Edit" && "$RESULT_FIELD" == "success" ]]; then
        pass "Outcome log format: timestamp, tool, result, file"
    else
        fail "Unexpected format (fields=$FIELD_COUNT, tool=$TOOL_FIELD, result=$RESULT_FIELD): $LINE"
    fi
else
    fail "No outcomes.log to check format"
fi

# ---- Test 3: Write tool detected correctly ----
echo "Test 3: Write tool detected when no old_string"

"$PLUGIN_DIR/scripts/post-edit-check.sh" \
    "{\"file_path\": \"$TEST_DIR/src/api/handlers.ts\", \"content\": \"hello\"}" \
    >/dev/null 2>&1 || true

if [[ -f "$OUTCOMES_LOG" ]]; then
    LINE=$(tail -1 "$OUTCOMES_LOG")
    TOOL_FIELD=$(echo "$LINE" | awk -F'\t' '{print $2}')
    if [[ "$TOOL_FIELD" == "Write" ]]; then
        pass "Write tool detected from JSON without old_string"
    else
        fail "Expected Write, got: $TOOL_FIELD"
    fi
else
    fail "No outcomes.log after Write test"
fi

# ---- Test 4: capture-tool-failure.sh writes failure to outcomes.log ----
echo "Test 4: capture-tool-failure.sh logs failure outcome"

# Clear log to isolate this test
> "$OUTCOMES_LOG"

FAILURE_INPUT='{"tool_name":"Edit","tool_input":{"file_path":"'"$TEST_DIR"'/src/api/handlers.ts","old_string":"nonexistent","new_string":"replacement"}}'
echo "$FAILURE_INPUT" | "$PLUGIN_DIR/scripts/capture-tool-failure.sh" >/dev/null 2>&1 || true

if [[ -f "$OUTCOMES_LOG" && -s "$OUTCOMES_LOG" ]]; then
    LINE=$(tail -1 "$OUTCOMES_LOG")
    RESULT_FIELD=$(echo "$LINE" | awk -F'\t' '{print $3}')
    TOOL_FIELD=$(echo "$LINE" | awk -F'\t' '{print $2}')
    if [[ "$RESULT_FIELD" == "failure" && "$TOOL_FIELD" == "Edit" ]]; then
        pass "capture-tool-failure.sh logs failure outcome"
    else
        fail "Expected failure/Edit, got: $RESULT_FIELD/$TOOL_FIELD"
    fi
else
    fail "No failure outcome logged"
fi

# Clean up skeleton reports from failure test
rm -f "$TEST_DIR/.intent-layer/mistakes/pending/SKELETON-"*.md 2>/dev/null || true

# ---- Test 5: Opt-out via disable-telemetry ----
echo "Test 5: Opt-out with disable-telemetry file"

# Clear log
> "$OUTCOMES_LOG"

# Create opt-out file
touch "$TEST_DIR/.intent-layer/disable-telemetry"

"$PLUGIN_DIR/scripts/post-edit-check.sh" \
    "{\"file_path\": \"$TEST_DIR/src/api/handlers.ts\", \"old_string\": \"a\", \"new_string\": \"b\"}" \
    >/dev/null 2>&1 || true

if [[ ! -s "$OUTCOMES_LOG" ]]; then
    pass "No outcome logged when disable-telemetry exists"
else
    fail "Outcome was logged despite disable-telemetry"
fi

# Also test failure hook opt-out
FAILURE_INPUT='{"tool_name":"Edit","tool_input":{"file_path":"'"$TEST_DIR"'/src/api/handlers.ts","old_string":"x","new_string":"y"}}'
echo "$FAILURE_INPUT" | "$PLUGIN_DIR/scripts/capture-tool-failure.sh" >/dev/null 2>&1 || true

if [[ ! -s "$OUTCOMES_LOG" ]]; then
    pass "Failure hook respects disable-telemetry"
else
    fail "Failure hook logged despite disable-telemetry"
fi

# Remove opt-out for remaining tests
rm "$TEST_DIR/.intent-layer/disable-telemetry"
rm -f "$TEST_DIR/.intent-layer/mistakes/pending/SKELETON-"*.md 2>/dev/null || true

# ---- Test 6: Log rotation at 1000 lines ----
echo "Test 6: Log rotation"

# Write 1050 lines
> "$OUTCOMES_LOG"
for i in $(seq 1 1050); do
    printf '2026-02-15T10:00:%02dZ\tEdit\tsuccess\t/fake/file.ts\n' $((i % 60)) >> "$OUTCOMES_LOG"
done

LINE_COUNT=$(wc -l < "$OUTCOMES_LOG" | tr -d ' ')
if [[ "$LINE_COUNT" -eq 1050 ]]; then
    # Trigger rotation by running the hook
    "$PLUGIN_DIR/scripts/post-edit-check.sh" \
        "{\"file_path\": \"$TEST_DIR/src/api/handlers.ts\", \"old_string\": \"a\", \"new_string\": \"b\"}" \
        >/dev/null 2>&1 || true

    LINE_COUNT_AFTER=$(wc -l < "$OUTCOMES_LOG" | tr -d ' ')
    if [[ "$LINE_COUNT_AFTER" -le 502 ]]; then
        pass "Log rotated from 1050 to $LINE_COUNT_AFTER lines"
    else
        fail "Expected ~501 lines after rotation, got $LINE_COUNT_AFTER"
    fi
else
    fail "Setup error: expected 1050 lines, got $LINE_COUNT"
fi

# ---- Test 7: show_telemetry.sh with sample data ----
echo "Test 7: show_telemetry.sh displays dashboard"

# Set up clean log data
mkdir -p "$TEST_DIR/.intent-layer/hooks"

TS="2026-02-15T10:00:00Z"

# Injections: some edits were covered
cat > "$TEST_DIR/.intent-layer/hooks/injections.log" << EOF
${TS}	${TEST_DIR}/src/api/handlers.ts	${TEST_DIR}/src/api/AGENTS.md	Pitfalls
${TS}	${TEST_DIR}/src/api/handlers.ts	${TEST_DIR}/src/api/AGENTS.md	Pitfalls
EOF

# Outcomes: mix of success/failure, covered/uncovered
cat > "$TEST_DIR/.intent-layer/hooks/outcomes.log" << EOF
${TS}	Edit	success	${TEST_DIR}/src/api/handlers.ts
${TS}	Edit	failure	${TEST_DIR}/src/api/handlers.ts
2026-02-15T10:01:00Z	Write	success	${TEST_DIR}/src/utils/helper.ts
2026-02-15T10:02:00Z	Edit	success	${TEST_DIR}/src/utils/helper.ts
EOF

output=$("$PLUGIN_DIR/scripts/show_telemetry.sh" "$TEST_DIR" 2>&1)

# Check for expected sections
CHECKS_PASSED=true

if ! echo "$output" | grep -q "Intent Layer Telemetry"; then
    fail "Missing header"
    CHECKS_PASSED=false
fi

if ! echo "$output" | grep -q "Total edits: 4"; then
    fail "Wrong total edits in: $output"
    CHECKS_PASSED=false
fi

if ! echo "$output" | grep -q "Per-Node Success Rates"; then
    fail "Missing per-node section"
    CHECKS_PASSED=false
fi

if ! echo "$output" | grep -q "AGENTS.md"; then
    fail "Missing node name in output"
    CHECKS_PASSED=false
fi

if ! echo "$output" | grep -q "Coverage Gaps"; then
    fail "Missing coverage gaps section"
    CHECKS_PASSED=false
fi

if $CHECKS_PASSED; then
    pass "show_telemetry.sh displays complete dashboard"
fi

# ---- Test 8: show_telemetry.sh with empty/missing logs ----
echo "Test 8: show_telemetry.sh handles missing data"

EMPTY_DIR=$(mktemp -d)
output=$("$PLUGIN_DIR/scripts/show_telemetry.sh" "$EMPTY_DIR" 2>&1 || true)
exit_code=0
"$PLUGIN_DIR/scripts/show_telemetry.sh" "$EMPTY_DIR" >/dev/null 2>&1 || exit_code=$?

if [[ "$exit_code" -eq 2 ]] && echo "$output" | grep -q "No telemetry data"; then
    pass "Graceful exit with no data (exit code 2)"
else
    fail "Expected exit 2 and message, got exit=$exit_code output=$output"
fi
rm -rf "$EMPTY_DIR"

# ---- Test 9: show_telemetry.sh --help ----
echo "Test 9: show_telemetry.sh --help"

output=$("$PLUGIN_DIR/scripts/show_telemetry.sh" --help 2>&1 || true)
if echo "$output" | grep -q "USAGE"; then
    pass "show_telemetry.sh --help works"
else
    fail "--help should show USAGE"
fi

# ---- Test 10: show_telemetry.sh bad args ----
echo "Test 10: show_telemetry.sh rejects bad args"

exit_code=0
"$PLUGIN_DIR/scripts/show_telemetry.sh" --bogus 2>/dev/null || exit_code=$?

if [[ "$exit_code" -eq 1 ]]; then
    pass "Bad args exit with code 1"
else
    fail "Expected exit 1 for bad args, got $exit_code"
fi

# ---- Test 11: No .intent-layer directory skips logging ----
echo "Test 11: No logging without .intent-layer directory"

CLEAN_DIR=$(mktemp -d)
export CLAUDE_PROJECT_DIR="$CLEAN_DIR"
mkdir -p "$CLEAN_DIR/src"
echo "# Root" > "$CLEAN_DIR/CLAUDE.md"
touch "$CLEAN_DIR/src/file.ts"

"$PLUGIN_DIR/scripts/post-edit-check.sh" \
    "{\"file_path\": \"$CLEAN_DIR/src/file.ts\", \"old_string\": \"a\", \"new_string\": \"b\"}" \
    >/dev/null 2>&1 || true

if [[ ! -d "$CLEAN_DIR/.intent-layer" ]]; then
    pass "No .intent-layer created on clean project"
else
    fail ".intent-layer directory was created unexpectedly"
fi

rm -rf "$CLEAN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# ============================================================
# Summary
# ============================================================
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[[ "$FAILED" -gt 0 ]] && exit 1
echo "All tests passed!"
