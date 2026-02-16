#!/usr/bin/env bash
# Tests for PreToolUse session deduplication
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
TEST_DIR=""
ORIG_TMPDIR="${TMPDIR:-/tmp}"
PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

cleanup() {
    [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
    # Clean up dedup files created during tests
    rm -f "${ORIG_TMPDIR}/intent-layer-dedup-test-session-"* 2>/dev/null || true
}
trap cleanup EXIT

echo "=== PreToolUse Dedup Tests ==="
echo ""

# ============================================================
# Fixture: project with a covering AGENTS.md
# ============================================================
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"
export TMPDIR="$ORIG_TMPDIR"

mkdir -p "$TEST_DIR/.intent-layer/hooks"
mkdir -p "$TEST_DIR/src/api"

cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

## Intent Layer

### Downlinks

| Area | Node |
|------|------|
| src | src/AGENTS.md |
EOF

cat > "$TEST_DIR/src/AGENTS.md" << 'EOF'
# Source Module

## Pitfalls

### Watch out for nulls
Check for null before dereferencing.

## Patterns

### Use early returns
Prefer guard clauses over nested conditionals.
EOF

# Create a real file to edit
echo "const x = 1;" > "$TEST_DIR/src/api/handler.ts"

# Helper: run PreToolUse hook with an Edit tool input
run_pretooluse() {
    local file_path="$1"
    echo "{\"hook_event_name\": \"PreToolUse\", \"tool_name\": \"Edit\", \"tool_input\": {\"file_path\": \"$file_path\"}}" | \
        "$PLUGIN_DIR/scripts/pre-edit-check.sh" 2>/dev/null || true
}

# ============================================================
# Test 1: First injection produces full output
# ============================================================

export CLAUDE_SESSION_ID="test-session-first"
# Remove any stale dedup file
rm -f "${TMPDIR}/intent-layer-dedup-test-session-first" 2>/dev/null || true

output=$(run_pretooluse "$TEST_DIR/src/api/handler.ts")

if echo "$output" | grep -q "Pitfalls"; then
    pass "First injection produces full output"
else
    fail "First injection should include Pitfalls section, got: $output"
fi

# ============================================================
# Test 2: Same node within 5 min produces no output (deduped)
# ============================================================

output2=$(run_pretooluse "$TEST_DIR/src/api/handler.ts")

if [[ -z "$output2" ]]; then
    pass "Same node within 5 min is deduped (no output)"
else
    fail "Should be silent on dedup, got: $output2"
fi

# ============================================================
# Test 3: Different session key produces separate output
# ============================================================

export CLAUDE_SESSION_ID="test-session-different"
rm -f "${TMPDIR}/intent-layer-dedup-test-session-different" 2>/dev/null || true

output3=$(run_pretooluse "$TEST_DIR/src/api/handler.ts")

if echo "$output3" | grep -q "Pitfalls"; then
    pass "Different session key gets full injection"
else
    fail "Different session should produce output, got: $output3"
fi

# ============================================================
# Test 4: Expired dedup entry (>5 min) triggers full injection
# ============================================================

export CLAUDE_SESSION_ID="test-session-expired"
DEDUP_FILE="${TMPDIR}/intent-layer-dedup-test-session-expired"
rm -f "$DEDUP_FILE" 2>/dev/null || true

# Write a dedup entry with a timestamp 6 minutes ago
OLD_TS=$(( $(date +%s) - 360 ))
printf '%s\t%s\n' "$TEST_DIR/src/AGENTS.md" "$OLD_TS" > "$DEDUP_FILE"

output4=$(run_pretooluse "$TEST_DIR/src/api/handler.ts")

if echo "$output4" | grep -q "Pitfalls"; then
    pass "Expired entry (>5 min) triggers full injection"
else
    fail "Expired entry should allow injection, got: $output4"
fi

# ============================================================
# Test 5: Dedup file is created after first injection
# ============================================================

export CLAUDE_SESSION_ID="test-session-filecreated"
DEDUP_FILE="${TMPDIR}/intent-layer-dedup-test-session-filecreated"
rm -f "$DEDUP_FILE" 2>/dev/null || true

run_pretooluse "$TEST_DIR/src/api/handler.ts" > /dev/null

if [[ -f "$DEDUP_FILE" ]]; then
    pass "Dedup file created after injection"
else
    fail "Dedup file should exist at: $DEDUP_FILE"
fi

# Verify it contains the node path and a timestamp
if grep -q "$TEST_DIR/src/AGENTS.md" "$DEDUP_FILE"; then
    pass "Dedup file contains node path"
else
    fail "Dedup file missing node path"
fi

# ============================================================
# Test 6: SessionStart cleanup removes stale dedup files
# ============================================================

# Create a fake old dedup file
OLD_DEDUP="${TMPDIR}/intent-layer-dedup-test-session-stale"
echo "some-node	1700000000" > "$OLD_DEDUP"
# Make it old (use touch with a past date)
touch -t 202301010000 "$OLD_DEDUP" 2>/dev/null || true

# Run SessionStart hook
"$PLUGIN_DIR/scripts/inject-learnings.sh" < /dev/null > /dev/null 2>&1 || true

if [[ ! -f "$OLD_DEDUP" ]]; then
    pass "SessionStart cleanup removes stale dedup files"
else
    fail "Stale dedup file should have been cleaned up"
fi

# ============================================================
# Test 7: Fallback to CLAUDE_PROJECT_DIR when no session ID
# ============================================================

unset CLAUDE_SESSION_ID
export CLAUDE_PROJECT_DIR="$TEST_DIR"
# Compute expected key
EXPECTED_KEY=$(printf '%s' "$TEST_DIR" | sed 's/[^A-Za-z0-9_-]/-/g')
DEDUP_FILE="${TMPDIR}/intent-layer-dedup-${EXPECTED_KEY}"
rm -f "$DEDUP_FILE" 2>/dev/null || true

run_pretooluse "$TEST_DIR/src/api/handler.ts" > /dev/null

if [[ -f "$DEDUP_FILE" ]]; then
    pass "Fallback to CLAUDE_PROJECT_DIR creates dedup file"
else
    fail "Should fallback to CLAUDE_PROJECT_DIR for dedup key"
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo "Results: $PASSED passed, $FAILED failed"

if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
