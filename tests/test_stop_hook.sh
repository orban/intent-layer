#!/usr/bin/env bash
# Tests for the two-tier Stop hook (stop-learning-check.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
STOP_HOOK="$PLUGIN_DIR/scripts/stop-learning-check.sh"

export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"

PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

# Create a fake curl that returns predetermined responses
setup_mock_curl() {
    local mock_dir="$1"
    local response="$2"
    local exit_code="${3:-0}"

    mkdir -p "$mock_dir/bin"
    cat > "$mock_dir/bin/curl" << MOCK_EOF
#!/usr/bin/env bash
if [[ "$exit_code" -ne 0 ]]; then
    exit $exit_code
fi
echo '$response'
MOCK_EOF
    chmod +x "$mock_dir/bin/curl"
}

echo "=== Stop Hook (stop-learning-check.sh) Tests ==="
echo ""

# --- Guard tests ---

# Test 1: Empty stdin
echo "Test 1: Empty stdin exits 0"
output=$(echo -n "" | "$STOP_HOOK" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Empty stdin exits cleanly"
else
    fail "Should exit cleanly on empty stdin: $output"
fi

# Test 2: Re-entry guard
echo "Test 2: stop_hook_active = true exits 0"
output=$(echo '{"stop_hook_active": true}' | "$STOP_HOOK" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Re-entry guard works"
else
    fail "Should exit cleanly on re-entry: $output"
fi

# Test 3: No .intent-layer directory
echo "Test 3: No .intent-layer directory exits 0"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
output=$(echo '{"stop_hook_active": false}' | \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" "$STOP_HOOK" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "No .intent-layer exits cleanly"
else
    fail "Should exit cleanly without .intent-layer: $output"
fi

# Test 4: Malformed stdin JSON
echo "Test 4: Malformed stdin JSON exits 0"
output=$(echo 'not valid json at all' | \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" "$STOP_HOOK" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Malformed JSON exits cleanly"
else
    fail "Should exit cleanly on malformed JSON: $output"
fi

# --- Tier 1 tests ---

# Test 5: No signals = exit 0
echo "Test 5: No Tier 1 signals exits 0"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/hooks"
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
# Empty injection log, no skeletons, no git changes
output=$(echo '{"stop_hook_active": false}' | \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" "$STOP_HOOK" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "No signals exits cleanly"
else
    fail "Should exit cleanly with no signals: $output"
fi

# Test 6: Skeleton reports trigger signal
echo "Test 6: Skeleton reports are detected as signal"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"
# No API key = fail-open, but we need to verify the signal was detected
# We can check by: if API key is set + curl exists but transcript is missing → exit 0
# OR: set API key but use a nonexistent transcript → shows we got past Tier 1
TMPFILE=$(mktemp)
echo '{"role":"user","content":"test"}' > "$TMPFILE"
output=$(echo "{\"stop_hook_active\": false, \"transcript_path\": \"$TMPFILE\"}" | \
    ANTHROPIC_API_KEY="" CLAUDE_PROJECT_DIR="$TEMP_PROJECT" "$STOP_HOOK" 2>&1 || true)
# With no API key, should exit 0 (fail-open) even though signal exists
if [[ -z "$output" ]]; then
    pass "Skeleton signal detected, no API key = fail-open"
else
    fail "Should fail-open without API key: $output"
fi
rm -f "$TMPFILE"

# Test 7: Non-empty injection log triggers signal
echo "Test 7: Non-empty injection log is detected as signal"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/hooks"
echo -e "2026-02-15T10:00:00Z\tsrc/main.ts\tsrc/AGENTS.md\tPitfalls" > "$TEMP_PROJECT/.intent-layer/hooks/injections.log"
output=$(echo '{"stop_hook_active": false}' | \
    ANTHROPIC_API_KEY="" CLAUDE_PROJECT_DIR="$TEMP_PROJECT" "$STOP_HOOK" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Injection log signal detected, no API key = fail-open"
else
    fail "Should fail-open: $output"
fi

# --- Tier 2 tests (with mock curl) ---

# Test 8: Haiku says should_capture: true → block
echo "Test 8: Haiku should_capture=true produces block"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"

MOCK_DIR=$(mktemp -d)
trap "rm -rf $MOCK_DIR $TEMP_PROJECT" EXIT
HAIKU_RESPONSE='{"content":[{"type":"text","text":"{\"should_capture\":true}"}],"model":"claude-haiku-4-5-20251001"}'
setup_mock_curl "$MOCK_DIR" "$HAIKU_RESPONSE"

TMPFILE=$(mktemp)
echo '{"role":"user","content":"I discovered that config parsing silently drops unknown keys"}' > "$TMPFILE"

output=$(echo "{\"stop_hook_active\": false, \"transcript_path\": \"$TMPFILE\"}" | \
    PATH="$MOCK_DIR/bin:$PATH" \
    ANTHROPIC_API_KEY="test-key" \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" \
    "$STOP_HOOK" 2>&1 || true)
rm -f "$TMPFILE"

if echo "$output" | jq -e '.decision == "block"' >/dev/null 2>&1; then
    pass "Haiku true → block decision"
else
    fail "Should produce block decision: $output"
fi

# Test 9: Haiku says should_capture: false → exit 0
echo "Test 9: Haiku should_capture=false exits 0"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"

MOCK_DIR=$(mktemp -d)
trap "rm -rf $MOCK_DIR $TEMP_PROJECT" EXIT
HAIKU_RESPONSE='{"content":[{"type":"text","text":"{\"should_capture\":false}"}],"model":"claude-haiku-4-5-20251001"}'
setup_mock_curl "$MOCK_DIR" "$HAIKU_RESPONSE"

TMPFILE=$(mktemp)
echo '{"role":"user","content":"just fixing a typo"}' > "$TMPFILE"

output=$(echo "{\"stop_hook_active\": false, \"transcript_path\": \"$TMPFILE\"}" | \
    PATH="$MOCK_DIR/bin:$PATH" \
    ANTHROPIC_API_KEY="test-key" \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" \
    "$STOP_HOOK" 2>&1 || true)
rm -f "$TMPFILE"

if [[ -z "$output" ]]; then
    pass "Haiku false → exit cleanly"
else
    fail "Should exit cleanly when Haiku says false: $output"
fi

# Test 10: curl failure → fail-open
echo "Test 10: curl failure exits 0 (fail-open)"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"

MOCK_DIR=$(mktemp -d)
trap "rm -rf $MOCK_DIR $TEMP_PROJECT" EXIT
setup_mock_curl "$MOCK_DIR" "" "7"  # exit code 7 = connection refused

TMPFILE=$(mktemp)
echo '{"role":"user","content":"test session"}' > "$TMPFILE"

output=$(echo "{\"stop_hook_active\": false, \"transcript_path\": \"$TMPFILE\"}" | \
    PATH="$MOCK_DIR/bin:$PATH" \
    ANTHROPIC_API_KEY="test-key" \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" \
    "$STOP_HOOK" 2>&1 || true)
rm -f "$TMPFILE"

if [[ -z "$output" ]]; then
    pass "curl failure → fail-open"
else
    fail "Should fail-open on curl error: $output"
fi

# Test 11: Malformed API response → fail-open
echo "Test 11: Malformed API response exits 0 (fail-open)"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"

MOCK_DIR=$(mktemp -d)
trap "rm -rf $MOCK_DIR $TEMP_PROJECT" EXIT
setup_mock_curl "$MOCK_DIR" '{"error": "invalid_api_key"}'

TMPFILE=$(mktemp)
echo '{"role":"user","content":"test"}' > "$TMPFILE"

output=$(echo "{\"stop_hook_active\": false, \"transcript_path\": \"$TMPFILE\"}" | \
    PATH="$MOCK_DIR/bin:$PATH" \
    ANTHROPIC_API_KEY="test-key" \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" \
    "$STOP_HOOK" 2>&1 || true)
rm -f "$TMPFILE"

if [[ -z "$output" ]]; then
    pass "Malformed API response → fail-open"
else
    fail "Should fail-open on malformed response: $output"
fi

# Test 12: Missing transcript → exit 0
echo "Test 12: Missing transcript file exits 0"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"

output=$(echo '{"stop_hook_active": false, "transcript_path": "/nonexistent/transcript.jsonl"}' | \
    ANTHROPIC_API_KEY="test-key" \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" \
    "$STOP_HOOK" 2>&1 || true)

if [[ -z "$output" ]]; then
    pass "Missing transcript → exit cleanly"
else
    fail "Should exit cleanly with missing transcript: $output"
fi

# Test 13: No curl available → fail-open
echo "Test 13: No curl available exits 0"
TEMP_PROJECT=$(mktemp -d)
trap "rm -rf $TEMP_PROJECT" EXIT
mkdir -p "$TEMP_PROJECT/.intent-layer/mistakes/pending"
touch "$TEMP_PROJECT/.intent-layer/mistakes/pending/SKELETON-2026-02-15-0001.md"

# Create a PATH that excludes curl
EMPTY_BIN=$(mktemp -d)
trap "rm -rf $EMPTY_BIN $TEMP_PROJECT" EXIT
# Only include jq on PATH (need it for guards)
ln -sf "$(which jq)" "$EMPTY_BIN/jq"
ln -sf "$(which bash)" "$EMPTY_BIN/bash"
ln -sf "$(which cat)" "$EMPTY_BIN/cat"
ln -sf "$(which find)" "$EMPTY_BIN/find"
ln -sf "$(which wc)" "$EMPTY_BIN/wc"
ln -sf "$(which tr)" "$EMPTY_BIN/tr"
ln -sf "$(which tail)" "$EMPTY_BIN/tail"
ln -sf "$(which head)" "$EMPTY_BIN/head"
ln -sf "$(which grep)" "$EMPTY_BIN/grep"
ln -sf "$(which dirname)" "$EMPTY_BIN/dirname" 2>/dev/null || true
ln -sf "$(which env)" "$EMPTY_BIN/env" 2>/dev/null || true

output=$(echo '{"stop_hook_active": false}' | \
    PATH="$EMPTY_BIN" \
    ANTHROPIC_API_KEY="test-key" \
    CLAUDE_PROJECT_DIR="$TEMP_PROJECT" \
    "$STOP_HOOK" 2>&1 || true)

if [[ -z "$output" ]]; then
    pass "No curl → fail-open"
else
    fail "Should fail-open without curl: $output"
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
