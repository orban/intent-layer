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

# ============================================================
# Fixture: project with root, child (api), sibling (core)
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

# Child node: src/api/
mkdir -p "$TEST_DIR/src/api"
cat > "$TEST_DIR/src/api/AGENTS.md" << 'EOF'
# API Module

## Pitfalls

### validate() silently passes on empty input

Always check input length before calling validate().
EOF

touch "$TEST_DIR/src/api/handlers.ts"

# Sibling node: src/core/
mkdir -p "$TEST_DIR/src/core"
cat > "$TEST_DIR/src/core/AGENTS.md" << 'EOF'
# Core Module

## Pitfalls

### Engine retry logic is not idempotent

Use transaction IDs to prevent duplicate processing.
EOF

touch "$TEST_DIR/src/core/engine.ts"

# Bare directory with no AGENTS.md anywhere above (except project root)
mkdir -p "$TEST_DIR/orphan/deep/nested"
touch "$TEST_DIR/orphan/deep/nested/file.ts"

echo "=== learn.sh Tests ==="
echo ""

# ---- Test 1: Direct write ----
echo "Test 1: Direct write appends pitfall to covering AGENTS.md"
"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pitfall \
    --title "Null check on empty collections" \
    --detail "API returns null instead of empty array for collections with no results" \
    >/dev/null 2>&1

AGENTS="$TEST_DIR/src/api/AGENTS.md"
has_title=false
has_body=false
grep -q "Null check on empty collections" "$AGENTS" && has_title=true
grep -q "null instead of empty array" "$AGENTS" && has_body=true

if $has_title && $has_body; then
    pass "Pitfall title AND body present in src/api/AGENTS.md"
else
    fail "title=$has_title body=$has_body"
fi

# ---- Test 2: Dedup skip ----
echo "Test 2: Near-duplicate title returns exit 2, AGENTS.md unchanged"
BEFORE_LINES=$(wc -l < "$AGENTS" | tr -d ' ')
EXIT_CODE=0
"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pitfall \
    --title "Null check on empty collections issue" \
    --detail "Duplicate of earlier finding" \
    2>/dev/null || EXIT_CODE=$?
AFTER_LINES=$(wc -l < "$AGENTS" | tr -d ' ')

if [[ "$EXIT_CODE" -eq 2 && "$BEFORE_LINES" -eq "$AFTER_LINES" ]]; then
    pass "Duplicate detected (exit 2), AGENTS.md line count unchanged ($BEFORE_LINES)"
else
    fail "exit=$EXIT_CODE before=$BEFORE_LINES after=$AFTER_LINES"
fi

# ---- Test 3: Type routing ----
echo "Test 3: Type routing — check→Checks, pattern→Patterns, insight→Context"
"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type check \
    --title "Verify auth middleware" \
    --detail "Run auth test suite before modifying middleware chain" \
    >/dev/null 2>&1

"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pattern \
    --title "Use middleware composition" \
    --detail "Compose handlers with pipe rather than nesting callbacks" \
    >/dev/null 2>&1

"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type insight \
    --title "Request validation runs twice" \
    --detail "Both middleware and handler validate - intentional defense in depth" \
    >/dev/null 2>&1

format_errors=""
grep -q "^## Checks" "$AGENTS" || format_errors="$format_errors no-Checks-section"
grep -q "\- \[ \]" "$AGENTS" || format_errors="$format_errors no-checklist-item"
grep -q "^## Patterns" "$AGENTS" || format_errors="$format_errors no-Patterns-section"
grep -q "\*\*Preferred\*\*" "$AGENTS" || format_errors="$format_errors no-Preferred-prefix"
grep -q "^## Context" "$AGENTS" || format_errors="$format_errors no-Context-section"
grep -q "defense in depth" "$AGENTS" || format_errors="$format_errors no-insight-body"

if [[ -z "$format_errors" ]]; then
    pass "All types routed to correct sections with proper formatting"
else
    fail "Format errors:$format_errors"
fi

# ---- Test 4: Missing node error ----
echo "Test 4: Path with no covering AGENTS.md returns exit 1"
# Create a truly isolated directory outside the project
ISOLATED_DIR=$(mktemp -d)
mkdir -p "$ISOLATED_DIR/nowhere"
touch "$ISOLATED_DIR/nowhere/file.ts"

EXIT_CODE=0
"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$ISOLATED_DIR" \
    --path "$ISOLATED_DIR/nowhere/file.ts" \
    --type pitfall \
    --title "Should fail" \
    --detail "No covering node" \
    2>/dev/null || EXIT_CODE=$?
rm -rf "$ISOLATED_DIR"

if [[ "$EXIT_CODE" -eq 1 ]]; then
    pass "Exit 1 when no covering AGENTS.md exists"
else
    fail "Expected exit 1, got $EXIT_CODE"
fi

# ---- Test 5: Section creation ----
echo "Test 5: Node without target section gets section created"
# src/core/AGENTS.md only has ## Pitfalls, not ## Checks
"$PLUGIN_DIR/scripts/learn.sh" \
    --project "$TEST_DIR" \
    --path "src/core/engine.ts" \
    --type check \
    --title "Verify idempotency key" \
    --detail "Check transaction ID uniqueness before retry" \
    >/dev/null 2>&1

CORE_AGENTS="$TEST_DIR/src/core/AGENTS.md"
has_section=false
has_entry=false
grep -q "^## Checks" "$CORE_AGENTS" && has_section=true
grep -q "Verify idempotency key" "$CORE_AGENTS" && has_entry=true

if $has_section && $has_entry; then
    pass "## Checks section created and entry appended"
else
    fail "section=$has_section entry=$has_entry"
fi

# ---- Test 6: Accumulation closure ----
echo "Test 6: learn.sh → resolve_context.sh → learning appears in output"
CONTEXT=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" 2>/dev/null)
has_learn_title=false
has_learn_body=false
echo "$CONTEXT" | grep -q "Null check on empty collections" && has_learn_title=true
echo "$CONTEXT" | grep -q "null instead of empty array" && has_learn_body=true

if $has_learn_title && $has_learn_body; then
    pass "Learning written by learn.sh appears in resolved context output"
else
    fail "title=$has_learn_title body=$has_learn_body"
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
