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

### Entry Points

| Task | Start Here |
|------|------------|
| Test | `src/api/index.ts` |

### Contracts
- All responses must be JSON.

### Pitfalls
- Token estimation uses bytes/4 approximation.

### Downlinks
- `src/api/AGENTS.md` - API
MD

# Child node (valid - includes Pitfalls as required)
mkdir -p "$TEMP_PROJECT/src/api"
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

## Purpose
Owns: API handlers.

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `handlers.ts` |

## Contracts
- Requests must be authenticated.

## Pitfalls
- Rate limiting applies to all endpoints.

## Patterns
### Adding a handler
1. Add route.
2. Add handler.

## Code Map
### Find It Fast
| Looking for... | Go to |
|---|---|
| Handler | `handlers.ts` |
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

# Test 2: Root missing Entry Points should error
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Missing entry points.

### Contracts
- All responses must be JSON.

### Pitfalls
- Watch out.

### Downlinks
- `src/api/AGENTS.md` - API
MD

status=0
output=$(run_validate "$TEMP_PROJECT/CLAUDE.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -q "Entry Points\|Subsystems"; then
    pass "Root schema enforcement catches missing Entry Points/Subsystems"
else
    fail "Root schema enforcement failed (status=$status): $output"
fi

# Test 3: Root missing Contracts should error
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Missing contracts.

### Entry Points

| Task | Start Here |
|------|------------|
| Test | `src/api/index.ts` |

### Pitfalls
- Watch out.

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

# Test 4: Root missing Pitfalls should error
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Missing pitfalls.

### Entry Points

| Task | Start Here |
|------|------------|
| Test | `src/api/index.ts` |

### Contracts
- All responses must be JSON.

### Downlinks
- `src/api/AGENTS.md` - API
MD

status=0
output=$(run_validate "$TEMP_PROJECT/CLAUDE.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Pitfalls"; then
    pass "Root missing Pitfalls is an error"
else
    fail "Root missing Pitfalls not caught (status=$status): $output"
fi

# Test 5: Child missing Pitfalls should error
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

## Purpose
Owns: API handlers.

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `handlers.ts` |

## Contracts
- Requests must be authenticated.

## Patterns
### Adding a handler
1. Add route.
MD

# Restore valid root for child tests
cat > "$TEMP_PROJECT/CLAUDE.md" << 'MD'
## Intent Layer

> TL;DR: Test project.

### Entry Points

| Task | Start Here |
|------|------------|
| Test | `src/api/index.ts` |

### Contracts
- All responses must be JSON.

### Pitfalls
- Token estimation uses bytes/4 approximation.

### Downlinks
- `src/api/AGENTS.md` - API
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Pitfalls"; then
    pass "Child missing Pitfalls is an error"
else
    fail "Child missing Pitfalls not caught (status=$status): $output"
fi

# Test 6: Child with Patterns but no Pitfalls should error
# (Same fixture as Test 5 - has Patterns but not Pitfalls)
if [[ $status -ne 0 ]] && echo "$output" | grep -qi "Missing required section.*Pitfalls"; then
    pass "Child with Patterns but no Pitfalls is an error"
else
    fail "Child with Patterns but no Pitfalls not caught (status=$status): $output"
fi

# Test 7: List exceeding 5 items should warn (exit 0)
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

## Purpose
Owns: API handlers.

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `handlers.ts` |

## Contracts
- Rule one.
- Rule two.
- Rule three.
- Rule four.
- Rule five.
- Rule six.

## Pitfalls
- Watch out.
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -qi "list items.*>5\|list items.*compressing"; then
    pass "List exceeding 5 items produces warning (exit 0)"
else
    fail "List exceeding 5 items check failed (status=$status): $output"
fi

# Test 8: Pitfall without source reference should produce warning (exit 0)
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

## Purpose
Owns: API handlers.

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `handlers.ts` |

## Contracts
- Requests must be authenticated. Source: security policy

## Pitfalls
- Something vague without any evidence.
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -qi "Pitfalls entries lack source references"; then
    pass "Pitfall without source reference produces warning (exit 0)"
else
    fail "Pitfall without source reference not warned (status=$status): $output"
fi

# Test 9: Pitfall WITH source reference should not warn for that entry
cat > "$TEMP_PROJECT/src/api/AGENTS.md" << 'MD'
# API

## Purpose
Owns: API handlers.

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `handlers.ts` |

## Contracts
- Requests must be authenticated. Source: security policy

## Pitfalls
- Rate limiting applies per `config/rate_limit.ts`.
- See PR #42 for details on the timeout bug.
MD

status=0
output=$(run_validate "$TEMP_PROJECT/src/api/AGENTS.md") || status=$?

if [[ $status -eq 0 ]] && ! echo "$output" | grep -qi "Pitfalls entries lack source references"; then
    pass "Pitfall with source references produces no evidence warning"
else
    fail "Pitfall with source references incorrectly warned (status=$status): $output"
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
