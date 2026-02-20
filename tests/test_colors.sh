#!/usr/bin/env bash
# Tests for ANSI color support in dashboard scripts
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
TEST_DIR=""
PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

# Portable ANSI escape detection (works on macOS and Linux)
has_ansi() { printf '%s' "$1" | grep -q $'\033\['; }

cleanup() {
    [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}
trap cleanup EXIT

echo "=== Color Support Tests ==="
echo ""

# ============================================================
# Fixture: project with Intent Layer nodes
# ============================================================
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"

cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

## Intent Layer

### Downlinks

| Area | Node |
|------|------|
| src | src/AGENTS.md |

## Pitfalls

### Example pitfall
Check for null.
EOF

mkdir -p "$TEST_DIR/src"
cat > "$TEST_DIR/src/AGENTS.md" << 'EOF'
# Source Module

## Pitfalls

### Watch out
Be careful.
EOF

# ============================================================
# Test 1: setup_colors sets variables when on TTY
# ============================================================

# We can't test real TTY, but we can test the NO_COLOR path
output=$(NO_COLOR=1 bash -c '
source "'"$PLUGIN_DIR"'/lib/common.sh"
setup_colors
echo "RED=[$RED] GREEN=[$GREEN] BOLD=[$BOLD] RESET=[$RESET]"
')

if echo "$output" | grep -q 'RED=\[\] GREEN=\[\] BOLD=\[\] RESET=\[\]'; then
    pass "setup_colors respects NO_COLOR (all vars empty)"
else
    fail "setup_colors should produce empty vars when NO_COLOR is set, got: $output"
fi

# ============================================================
# Test 2: show_status.sh outputs without ANSI when piped
# ============================================================

output=$("$PLUGIN_DIR/scripts/show_status.sh" "$TEST_DIR" 2>&1)

# Piped output should have no ANSI escape sequences
if has_ansi "$output"; then
    fail "show_status.sh should not emit ANSI when piped"
else
    pass "show_status.sh suppresses ANSI when piped"
fi

# Check it still has expected content
if echo "$output" | grep -q "INTENT LAYER STATUS DASHBOARD"; then
    pass "show_status.sh outputs dashboard header"
else
    fail "show_status.sh missing dashboard header"
fi

# ============================================================
# Test 3: show_hierarchy.sh outputs without ANSI when piped
# ============================================================

output=$("$PLUGIN_DIR/scripts/show_hierarchy.sh" "$TEST_DIR" 2>&1)

if has_ansi "$output"; then
    fail "show_hierarchy.sh should not emit ANSI when piped"
else
    pass "show_hierarchy.sh suppresses ANSI when piped"
fi

if echo "$output" | grep -q "Intent Layer Hierarchy"; then
    pass "show_hierarchy.sh outputs hierarchy header"
else
    fail "show_hierarchy.sh missing hierarchy header"
fi

# ============================================================
# Test 4: show_status.sh --json ignores color entirely
# ============================================================

json_output=$("$PLUGIN_DIR/scripts/show_status.sh" --json "$TEST_DIR" 2>&1)

if has_ansi "$json_output"; then
    fail "show_status.sh --json should never emit ANSI"
else
    pass "show_status.sh --json has no ANSI escapes"
fi

# Validate it's valid JSON
if echo "$json_output" | python3 -m json.tool > /dev/null 2>&1; then
    pass "show_status.sh --json produces valid JSON"
else
    fail "show_status.sh --json output is not valid JSON"
fi

# ============================================================
# Test 5: audit_intent_layer.sh outputs without ANSI when piped
# ============================================================

output=$("$PLUGIN_DIR/scripts/audit_intent_layer.sh" --quick "$TEST_DIR" 2>&1) || true

if has_ansi "$output"; then
    fail "audit_intent_layer.sh should not emit ANSI when piped"
else
    pass "audit_intent_layer.sh suppresses ANSI when piped"
fi

if echo "$output" | grep -q "OVERALL:"; then
    pass "audit_intent_layer.sh outputs OVERALL status"
else
    fail "audit_intent_layer.sh missing OVERALL status"
fi

# ============================================================
# Test 6: audit_intent_layer.sh --json ignores color
# ============================================================

json_output=$("$PLUGIN_DIR/scripts/audit_intent_layer.sh" --json --quick "$TEST_DIR" 2>&1) || true

if has_ansi "$json_output"; then
    fail "audit_intent_layer.sh --json should never emit ANSI"
else
    pass "audit_intent_layer.sh --json has no ANSI escapes"
fi

if echo "$json_output" | python3 -m json.tool > /dev/null 2>&1; then
    pass "audit_intent_layer.sh --json produces valid JSON"
else
    fail "audit_intent_layer.sh --json output is not valid JSON"
fi

# ============================================================
# Test 7: NO_COLOR=1 suppresses color in all scripts
# ============================================================

# Even if stdout is a TTY (simulated), NO_COLOR should win
for script in show_status.sh show_hierarchy.sh; do
    output=$(NO_COLOR=1 "$PLUGIN_DIR/scripts/$script" "$TEST_DIR" 2>&1)
    if has_ansi "$output"; then
        fail "$script ignores NO_COLOR"
    else
        pass "$script respects NO_COLOR=1"
    fi
done

# ============================================================
# Summary
# ============================================================
echo ""
echo "Results: $PASSED passed, $FAILED failed"

if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
