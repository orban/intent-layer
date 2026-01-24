#!/usr/bin/env bash
# Integration tests for learning layer hooks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

# Set environment for testing
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"

PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

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

# Test 2: PostToolUseFailure auto-captures Edit failure
echo "Test 2: PostToolUseFailure on Edit failure"
output=$(echo '{"hook_event_name": "PostToolUseFailure", "tool_name": "Edit", "tool_input": {"file_path": "/test.ts"}}' | \
    "$PLUGIN_DIR/scripts/capture-tool-failure.sh" 2>&1 || true)
if echo "$output" | grep -qi "Mistake Captured\|skeleton"; then
    pass "Auto-captures Edit failure"
else
    fail "Should auto-capture: $output"
fi
# Clean up any skeleton created during test
rm -f ./.intent-layer/mistakes/pending/SKELETON-*.md 2>/dev/null || true

# Test 3: PostToolUseFailure filters Read
echo "Test 3: PostToolUseFailure filters Read"
output=$(echo '{"hook_event_name": "PostToolUseFailure", "tool_name": "Read", "tool_input": {"file_path": "/test.md"}}' | \
    "$PLUGIN_DIR/scripts/capture-tool-failure.sh" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "Silently ignores Read failure"
else
    fail "Should be silent: $output"
fi

# Test 4: SessionStart hook runs
echo "Test 4: SessionStart hook runs"
if "$PLUGIN_DIR/scripts/inject-learnings.sh" < /dev/null >/dev/null 2>&1; then
    pass "SessionStart hook executes"
else
    fail "SessionStart hook crashed"
fi

# Test 5: PreToolUse handles Edit
echo "Test 5: PreToolUse handles Edit"
exit_code=0
echo '{"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "nonexistent/file.py"}}' | \
    "$PLUGIN_DIR/scripts/pre-edit-check.sh" >/dev/null 2>&1 || exit_code=$?
if [[ $exit_code -le 1 ]]; then
    pass "PreToolUse handles Edit without crashing"
else
    fail "PreToolUse crashed with exit code $exit_code"
fi

# Test 6: PreToolUse filters Read
echo "Test 6: PreToolUse filters Read"
output=$(echo '{"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "test.py"}}' | \
    "$PLUGIN_DIR/scripts/pre-edit-check.sh" 2>&1 || true)
if [[ -z "$output" ]]; then
    pass "PreToolUse ignores Read"
else
    fail "Should ignore Read: $output"
fi

# Test 7: hooks.json is valid and has correct structure
echo "Test 7: hooks.json validation"
if jq -e '.hooks.PostToolUse' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.PostToolUseFailure' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.SessionStart' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.PreToolUse' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1 && \
   jq -e '.hooks.Stop' "$PLUGIN_DIR/hooks/hooks.json" >/dev/null 2>&1; then
    pass "hooks.json has all 5 hook events"
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

# Test 10: SessionStart uses stronger language for missing Intent Layer
echo "Test 10: SessionStart uses stronger language"
TEMP_PROJECT=$(mktemp -d)
export CLAUDE_PROJECT_DIR="$TEMP_PROJECT"
output=$("$PLUGIN_DIR/scripts/inject-learnings.sh" 2>&1 || true)
if echo "$output" | grep -q "⚠️ Intent Layer: Not Configured"; then
    pass "SessionStart shows warning emoji for missing Intent Layer"
else
    fail "SessionStart should show ⚠️ for missing Intent Layer: $output"
fi
rm -rf "$TEMP_PROJECT"
unset CLAUDE_PROJECT_DIR

# Test 11: PostToolUse detects new directories
echo "Test 11: PostToolUse detects new directories"
TEMP_PROJECT=$(mktemp -d)
# Create parent with AGENTS.md (coverage exists)
mkdir -p "$TEMP_PROJECT/src"
echo "# AGENTS.md" > "$TEMP_PROJECT/src/AGENTS.md"
# Create new subdirectory with one file
mkdir -p "$TEMP_PROJECT/src/utils"
touch "$TEMP_PROJECT/src/utils/helper.ts"
# Run post-edit-check with the new file
output=$("$PLUGIN_DIR/scripts/post-edit-check.sh" "{\"file_path\": \"$TEMP_PROJECT/src/utils/helper.ts\"}" 2>&1 || true)
if echo "$output" | grep -q "📁 New directory"; then
    pass "PostToolUse detects new directory"
else
    fail "PostToolUse should detect new directory: $output"
fi
rm -rf "$TEMP_PROJECT"

# Test 12: PostToolUse ignores excluded directories
echo "Test 12: PostToolUse ignores excluded directories"
TEMP_PROJECT=$(mktemp -d)
mkdir -p "$TEMP_PROJECT/src"
echo "# AGENTS.md" > "$TEMP_PROJECT/src/AGENTS.md"
mkdir -p "$TEMP_PROJECT/src/node_modules/pkg"
touch "$TEMP_PROJECT/src/node_modules/pkg/index.js"
output=$("$PLUGIN_DIR/scripts/post-edit-check.sh" "{\"file_path\": \"$TEMP_PROJECT/src/node_modules/pkg/index.js\"}" 2>&1 || true)
if echo "$output" | grep -q "📁 New directory"; then
    fail "PostToolUse should ignore node_modules"
else
    pass "PostToolUse ignores excluded directory (node_modules)"
fi
rm -rf "$TEMP_PROJECT"

# Test 13: PostToolUse ignores established directories
echo "Test 13: PostToolUse ignores established directories"
TEMP_PROJECT=$(mktemp -d)
mkdir -p "$TEMP_PROJECT/src"
echo "# AGENTS.md" > "$TEMP_PROJECT/src/AGENTS.md"
mkdir -p "$TEMP_PROJECT/src/utils"
# Create 5 files to make it "established"
for i in 1 2 3 4 5; do
    touch "$TEMP_PROJECT/src/utils/file$i.ts"
done
output=$("$PLUGIN_DIR/scripts/post-edit-check.sh" "{\"file_path\": \"$TEMP_PROJECT/src/utils/file5.ts\"}" 2>&1 || true)
if echo "$output" | grep -q "📁 New directory"; then
    fail "PostToolUse should ignore established directory (5 files)"
else
    pass "PostToolUse ignores established directory"
fi
rm -rf "$TEMP_PROJECT"

# Test 14: All lib scripts have --help
echo "Test 14: Library scripts have --help"
failed_help=0
checked=0
for script in "$PLUGIN_DIR/lib"/*.sh; do
    if [[ -f "$script" && -x "$script" && "$(basename "$script")" != "common.sh" ]]; then
        checked=$((checked + 1))
        if ! "$script" --help >/dev/null 2>&1; then
            fail "Script missing --help: $(basename "$script")"
            failed_help=$((failed_help + 1))
        fi
    fi
done
if [[ $failed_help -eq 0 && $checked -gt 0 ]]; then
    pass "All lib scripts support --help ($checked checked)"
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
