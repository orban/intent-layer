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

# Setup: create a project with hierarchy
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"

# Root node
cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

> **TL;DR**: Test project for context resolution.

## Contracts

- All API calls must be authenticated
- Never log PII

## Pitfalls

- Config values are case-sensitive
EOF

# Child node
mkdir -p "$TEST_DIR/src/api"
cat > "$TEST_DIR/src/api/AGENTS.md" << 'EOF'
# API Module

## Purpose
Owns: REST endpoints and request validation.
Does not own: Business logic (see `src/core/`).

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `routes/` |
| Debug request | `middleware/debug.ts` |

## Contracts
- All endpoints return JSON
- Rate limiting via Redis

## Pitfalls
- `validate()` silently passes on empty input
- Route order matters — first match wins

## Checks
### Before modifying routes
- [ ] Run `make test-api`

## Patterns
### Adding a new endpoint
1. Create route in `routes/`
2. Add validation middleware
3. Register in `index.ts`
EOF

# Test 1: resolve_context.sh exists and is executable
echo "Test 1: Script exists and runs"
if [[ -x "$PLUGIN_DIR/scripts/resolve_context.sh" ]]; then
    pass "resolve_context.sh is executable"
else
    fail "resolve_context.sh not found or not executable"
fi

# Test 2: Returns context for a specific path
echo "Test 2: Resolves context for src/api/"
output=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" 2>/dev/null)
if echo "$output" | grep -q "All API calls must be authenticated"; then
    pass "Includes inherited contract from root"
else
    fail "Missing inherited contract: $output"
fi

# Test 3: Includes local node content
echo "Test 3: Includes local node sections"
if echo "$output" | grep -q "validate().*silently passes"; then
    pass "Includes local pitfall"
else
    fail "Missing local pitfall"
fi

# Test 4: Includes all section types
echo "Test 4: Includes Contracts, Pitfalls, Checks, Patterns"
missing=""
echo "$output" | grep -q "## Contracts" || missing="$missing Contracts"
echo "$output" | grep -q "## Pitfalls" || missing="$missing Pitfalls"
echo "$output" | grep -q "## Checks" || missing="$missing Checks"
echo "$output" | grep -q "## Patterns" || missing="$missing Patterns"
if [[ -z "$missing" ]]; then
    pass "All section types present"
else
    fail "Missing sections:$missing"
fi

# Test 5: Shows hierarchy (root → child)
echo "Test 5: Shows hierarchy path"
if echo "$output" | grep -q "CLAUDE.md" && echo "$output" | grep -q "src/api/AGENTS.md"; then
    pass "Shows both root and child in hierarchy"
else
    fail "Should show hierarchy path"
fi

# Test 6: Uncovered path returns warning
echo "Test 6: Uncovered path returns meaningful output"
mkdir -p "$TEST_DIR/orphan"
output=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "orphan/" 2>/dev/null || true)
if echo "$output" | grep -qi "no.*covering\|uncovered\|not found"; then
    pass "Uncovered path returns warning"
else
    fail "Should warn about uncovered path"
fi

# Test 7: --sections flag filters output
echo "Test 7: --sections flag filters to specific sections"
output=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" --sections "Contracts,Pitfalls" 2>/dev/null)
if echo "$output" | grep -q "## Contracts" && echo "$output" | grep -q "## Pitfalls"; then
    pass "--sections includes requested sections"
else
    fail "--sections filter failed"
fi
# Should NOT include Patterns when only Contracts,Pitfalls requested
if echo "$output" | grep -q "## Patterns"; then
    fail "--sections should exclude unrequested sections"
else
    pass "--sections excludes unrequested sections"
fi

# Test 8: --compact flag produces shorter output
echo "Test 8: --compact flag"
full=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" 2>/dev/null | wc -c | tr -d ' ')
compact=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" --compact 2>/dev/null | wc -c | tr -d ' ')
if [[ "$compact" -lt "$full" ]]; then
    pass "--compact produces shorter output"
else
    fail "--compact should be shorter than full (full=$full, compact=$compact)"
fi

# Test 9: Works with absolute file path too
echo "Test 9: Accepts absolute file path"
output=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "$TEST_DIR/src/api/routes/users.ts" 2>/dev/null)
if echo "$output" | grep -q "Rate limiting via Redis"; then
    pass "Works with absolute file path"
else
    fail "Should resolve context from absolute file path"
fi

# Summary
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[[ "$FAILED" -gt 0 ]] && exit 1
echo "All tests passed!"
