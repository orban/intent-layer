#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
SUGGEST="$PLUGIN_DIR/scripts/suggest_updates.sh"

PASSED=0
FAILED=0
TEST_DIR=""

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

cleanup() {
    [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}
trap cleanup EXIT

echo "=== suggest_updates.sh Tests ==="
echo ""

# ---- Test 1: --help works ----
echo "Test 1: --help exits 0 and shows usage"
status=0
output=$("$SUGGEST" --help 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "USAGE"; then
    pass "--help exits 0 and shows usage info"
else
    fail "--help status=$status"
fi

# ---- Test 2: -h also works ----
echo "Test 2: -h is an alias for --help"
status=0
output=$("$SUGGEST" -h 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "suggest_updates.sh"; then
    pass "-h exits 0 and shows script name"
else
    fail "-h status=$status"
fi

# ---- Setup: create isolated git repo for remaining tests ----
TEST_DIR=$(mktemp -d)

# Initialize a git repo with an Intent Layer structure
cd "$TEST_DIR"
git init -q
git config user.email "test@test.com"
git config user.name "Test"

# Create root CLAUDE.md with Intent Layer
cat > CLAUDE.md << 'MD'
# Test Project

## Intent Layer

> TL;DR: Test project.

### Entry Points

| Task | Start Here |
|------|------------|
| Test | `src/app.ts` |

### Contracts
- All responses must be JSON.

### Pitfalls
- Watch out for null values.

### Downlinks
- `src/AGENTS.md` - Source code
MD

# Create child node
mkdir -p src
cat > src/AGENTS.md << 'MD'
# Source

## Purpose
Application source code.

## Pitfalls
- Validate input before processing.
MD

# Create a source file
echo "const x = 1;" > src/app.ts

git add -A
git commit -q -m "initial commit"

# Create changes on a branch
git checkout -q -b test-branch
echo "const y = 2;" >> src/app.ts
echo "const z = 3;" > src/utils.ts
git add -A
git commit -q -m "add changes"

# ---- Test 3: Dry-run shows affected nodes ----
echo "Test 3: Dry-run mode shows affected nodes"
status=0
# Unset API key to force dry-run
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" main HEAD --dry-run 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "Dry-run mode" && echo "$output" | grep -q "Affected Nodes"; then
    pass "Dry-run mode shows affected nodes"
else
    fail "Dry-run mode failed (status=$status): $output"
fi

# ---- Test 4: No API key triggers dry-run automatically ----
echo "Test 4: Missing API key triggers dry-run"
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" main HEAD 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "Dry-run mode"; then
    pass "Missing API key triggers dry-run automatically"
else
    fail "Missing API key did not trigger dry-run (status=$status): $output"
fi

# ---- Test 5: No affected nodes exits with code 2 ----
echo "Test 5: No affected nodes exits with code 2"
# Compare HEAD to itself — no changes
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" HEAD HEAD 2>&1) || status=$?

if [[ $status -eq 2 ]] && echo "$output" | grep -qi "no affected"; then
    pass "No affected nodes exits with code 2"
else
    fail "Expected exit 2 for no changes, got status=$status: $output"
fi

# ---- Test 6: Invalid git ref exits with code 1 ----
echo "Test 6: Invalid git ref exits with code 1"
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" nonexistent-ref-xyz HEAD 2>&1) || status=$?

if [[ $status -eq 1 ]] && echo "$output" | grep -qi "invalid git ref"; then
    pass "Invalid git ref exits with code 1"
else
    fail "Expected exit 1 for invalid ref, got status=$status: $output"
fi

# ---- Test 7: Sensitive file filtering ----
echo "Test 7: Sensitive files are excluded from dry-run output"
# Create a commit with a .env file
git checkout -q test-branch
echo "SECRET=password123" > .env
echo "KEY=abc" > src/credentials.json
echo "real code" > src/real.ts
cat > src/secret.pem << 'PEM'
-----BEGIN RSA PRIVATE KEY-----
fakekeydata
-----END RSA PRIVATE KEY-----
PEM
git add -A
git commit -q -m "add sensitive and normal files"

# The dry-run output won't directly show filtered files (that's an API-path feature),
# but we can test the filter_sensitive_diff function indirectly by checking that
# the script doesn't crash when sensitive files are in the diff.
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" main HEAD --dry-run 2>&1) || status=$?

if [[ $status -eq 0 ]]; then
    pass "Script handles diffs containing sensitive files without error"
else
    fail "Script crashed with sensitive files in diff (status=$status): $output"
fi

# ---- Test 8: Output includes header and diff range ----
echo "Test 8: Output format includes header and diff range"
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" main HEAD --dry-run 2>&1) || status=$?

has_header=false
has_range=false
echo "$output" | grep -q "# Intent Layer Update Suggestions" && has_header=true
echo "$output" | grep -q "main..HEAD" && has_range=true

if $has_header && $has_range; then
    pass "Output includes markdown header and diff range"
else
    fail "header=$has_header range=$has_range"
fi

# ---- Test 9: Affected nodes list includes expected node ----
echo "Test 9: Affected nodes list includes src/AGENTS.md"
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" main HEAD --dry-run 2>&1) || status=$?

if echo "$output" | grep -q "src/AGENTS.md"; then
    pass "Affected nodes includes src/AGENTS.md"
else
    fail "src/AGENTS.md not in affected nodes: $output"
fi

# ---- Test 10: Unknown option exits with error ----
echo "Test 10: Unknown option exits with error"
status=0
output=$(ANTHROPIC_API_KEY="" "$SUGGEST" --unknown-flag 2>&1) || status=$?

if [[ $status -eq 1 ]] && echo "$output" | grep -q "Unknown option"; then
    pass "Unknown option exits with error"
else
    fail "Expected exit 1 for unknown option, got status=$status"
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
