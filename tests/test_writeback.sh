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

TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# Create minimal project
cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test
## Pitfalls
- Existing pitfall
EOF

# Test 1: Non-interactive capture with all flags
echo "Test 1: Non-interactive capture creates report"
cd "$TEST_DIR"
output=$("$PLUGIN_DIR/scripts/capture_mistake.sh" \
    --non-interactive \
    --type pitfall \
    --dir "$TEST_DIR" \
    --operation "Edit auth handler" \
    --what "Function uses arrow syntax not function declaration" \
    --cause "API module uses arrow functions exclusively" \
    2>&1 || true)
PENDING_DIR="$TEST_DIR/.intent-layer/mistakes/pending"
if ls "$PENDING_DIR"/PITFALL-*.md 1>/dev/null 2>&1; then
    pass "Non-interactive capture creates report"
else
    fail "No report created: $output"
fi

# Test 2: Report includes all provided fields
echo "Test 2: Report contains all fields"
REPORT=$(ls -1 "$PENDING_DIR"/PITFALL-*.md | head -1)
missing=""
grep -q "Edit auth handler" "$REPORT" || missing="$missing operation"
grep -q "arrow syntax" "$REPORT" || missing="$missing what"
grep -q "arrow functions" "$REPORT" || missing="$missing cause"
if [[ -z "$missing" ]]; then
    pass "Report contains all fields"
else
    fail "Report missing:$missing"
fi

# Test 3: --agent-id flag is recorded
echo "Test 3: Agent ID recorded in report"
rm -rf "$PENDING_DIR"
cd "$TEST_DIR"
"$PLUGIN_DIR/scripts/capture_mistake.sh" \
    --non-interactive \
    --type insight \
    --dir "$TEST_DIR" \
    --operation "Analyze codebase" \
    --what "Database uses soft deletes" \
    --cause "Records have deleted_at column" \
    --agent-id "swarm-worker-3" \
    2>&1 || true
REPORT=$(ls -1 "$PENDING_DIR"/INSIGHT-*.md 2>/dev/null | head -1)
if [[ -n "$REPORT" ]] && grep -q "swarm-worker-3" "$REPORT"; then
    pass "Agent ID recorded in report"
else
    fail "Agent ID not found in report"
fi

# Test 4: Multiple workers can write without conflicts
echo "Test 4: Concurrent writes don't conflict"
rm -rf "$PENDING_DIR"
for i in 1 2 3 4 5; do
    cd "$TEST_DIR"
    "$PLUGIN_DIR/scripts/capture_mistake.sh" \
        --non-interactive \
        --type pitfall \
        --dir "$TEST_DIR" \
        --operation "Worker $i task" \
        --what "Discovery $i" \
        --cause "Reason $i" \
        --agent-id "worker-$i" \
        2>&1 || true &
done
wait
COUNT=$(find "$PENDING_DIR" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$COUNT" -eq 5 ]]; then
    pass "5 concurrent writes produced 5 reports"
else
    fail "Expected 5 reports, got $COUNT"
fi

# Summary
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[[ "$FAILED" -gt 0 ]] && exit 1
echo "All tests passed!"
