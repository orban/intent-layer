#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

# Helper to run validate_node.sh and capture both output and exit status
run_validate() {
    local file="$1"
    local out
    local rc=0
    out=$("$PLUGIN_DIR/scripts/validate_node.sh" "$file" 2>&1) || rc=$?
    echo "$out"
    return $rc
}

TEMP_PROJECT=$(mktemp -d)
trap 'rm -rf "$TEMP_PROJECT"' EXIT

# Root node (valid - includes all required sections)
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Test project.

### Contracts
- All responses must be JSON.

### Rules
- Token estimation uses bytes/4 approximation. Source: `lib/tokens.ts`

### Downlinks
- `src/api/AGENTS.md` - API
MD

# Child node (valid - includes Contracts as required)
mkdir -p "$TEMP_PROJECT/src/api"
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

Owns: API handlers.

## Contracts
- Requests must be authenticated.

## Rules
- Rate limiting applies to all endpoints. Source: `config/rate_limit.ts`

## Boundaries
- Do not import from `../auth` directly.

## Ownership
- `handlers.ts` — request handlers
MD

# Test 1: Child node detection with relative path
pushd "$TEMP_PROJECT/src/api" >/dev/null
status=0
output=$(run_validate "AGENTS.md") || status=$?
popd >/dev/null

if echo "$output" | grep -q "Type: Child node" && [[ $status -eq 0 ]]; then
    pass "Child node validated as child with relative path"
else
    fail "Child node misclassified or failed (status=$status): $output"
fi

# Test 2: Root missing Downlinks should error
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Missing downlinks.

### Contracts
- All responses must be JSON.

### Rules
- Watch out. Source: `foo.ts`
MD

status=0
output=$(run_validate "$TEMP_PROJECT/CLAUDE.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Downlinks"; then
    pass "Root missing Downlinks is an error"
else
    fail "Root missing Downlinks not caught (status=$status): $output"
fi

# Test 3: Root missing Contracts should error
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Missing contracts.

### Rules
- Watch out. Source: `foo.ts`

### Downlinks
- `src/api/AGENTS.md` - API
MD

status=0
output=$(run_validate "$TEMP_PROJECT/CLAUDE.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Contracts"; then
    pass "Root missing Contracts is an error"
else
    fail "Root missing Contracts not caught (status=$status): $output"
fi

# Test 4: Root missing Intent Layer section should error
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
# Project

> TL;DR: Missing Intent Layer section.

## Contracts
- All responses must be JSON.

## Downlinks
- `src/api/AGENTS.md` - API
MD

status=0
output=$(run_validate "$TEMP_PROJECT/CLAUDE.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Intent Layer"; then
    pass "Root missing Intent Layer section is an error"
else
    fail "Root missing Intent Layer section not caught (status=$status): $output"
fi

# Test 5: Child missing Contracts should error
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

Owns: API handlers.

## Rules
- Rate limiting applies to all endpoints. Source: `config/rate_limit.ts`

## Boundaries
- Do not import from `../auth` directly.
MD

# Restore valid root for child tests
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Test project.

### Contracts
- All responses must be JSON.

### Rules
- Token estimation uses bytes/4 approximation. Source: `lib/tokens.ts`

### Downlinks
- `src/api/AGENTS.md` - API
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Contracts"; then
    pass "Child missing Contracts is an error"
else
    fail "Child missing Contracts not caught (status=$status): $output"
fi

# Test 6: Child with only Contracts should pass (Rules/Boundaries/Ownership are recommended, not required)
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

Owns: API handlers.

## Contracts
- Requests must be authenticated.
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]]; then
    pass "Child with only Contracts passes (other sections are recommended)"
else
    fail "Child with only Contracts should pass (status=$status): $output"
fi

# Verify it warns about missing recommended sections
if echo "$output" | grep -qi "Missing recommended section.*Rules"; then
    pass "Child without Rules gets recommendation warning"
else
    fail "Child without Rules should get recommendation warning: $output"
fi

# Test 7: List exceeding 5 items should warn (exit 0)
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

Owns: API handlers.

## Contracts
- Rule one.
- Rule two.
- Rule three.
- Rule four.
- Rule five.
- Rule six.

## Rules
- Watch out. Source: `foo.ts`
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -qi "list items.*>5\|list items.*compressing"; then
    pass "List exceeding 5 items produces warning (exit 0)"
else
    fail "List exceeding 5 items check failed (status=$status): $output"
fi

# Test 8: Rule without source reference should produce warning (exit 0)
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

Owns: API handlers.

## Contracts
- Requests must be authenticated. Source: security policy

## Rules
- Something vague without any evidence.
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -qi "Rules entries lack source references"; then
    pass "Rule without source reference produces warning (exit 0)"
else
    fail "Rule without source reference not warned (status=$status): $output"
fi

# Test 9: Rule WITH source reference should not warn for that entry
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

Owns: API handlers.

## Contracts
- Requests must be authenticated. Source: security policy

## Rules
- Rate limiting applies per `config/rate_limit.ts`.
- See PR #42 for details on the timeout bug.
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]] && ! echo "$output" | grep -qi "Rules entries lack source references"; then
    pass "Rule with source references produces no evidence warning"
else
    fail "Rule with source references incorrectly warned (status=$status): $output"
fi

# Test 10: Child token budget enforcement (>1500 tokens should error)
# 1500 tokens ≈ 6000 bytes. Generate a file just over that.
{
    echo "# API"
    echo ""
    echo "Owns: API handlers."
    echo ""
    echo "## Contracts"
    for i in $(seq 1 200); do
        echo "- Contract rule number $i must be followed at all times for safety."
    done
} > "$TEMP_PROJECT/src/api/AGENTS.md"

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "exceeds 1500 limit"; then
    pass "Child node exceeding 1500 token budget is an error"
else
    fail "Child node token budget not enforced (status=$status): $output"
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
