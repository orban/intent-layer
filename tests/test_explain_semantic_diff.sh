#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
EXPLAIN="$PLUGIN_DIR/scripts/explain_semantic_diff.sh"

PASSED=0
FAILED=0
TEST_DIR=""

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

cleanup() {
    [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}
trap cleanup EXIT

echo "=== explain_semantic_diff.sh Tests ==="
echo ""

echo "Test 1: --help exits 0 and shows usage"
status=0
output=$("$EXPLAIN" --help 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "USAGE"; then
    pass "--help exits 0 and shows usage"
else
    fail "--help status=$status"
fi

echo "Test 2: Invalid git ref exits with code 1"
status=0
output=$("$EXPLAIN" nonexistent-ref HEAD 2>&1) || status=$?

if [[ $status -eq 1 ]] && echo "$output" | grep -qi "invalid git ref"; then
    pass "Invalid git ref exits with code 1"
else
    fail "Expected exit 1 for invalid ref, got status=$status"
fi

TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"
git init -q
git branch -M main
git config user.email "test@test.com"
git config user.name "Test User"
git config commit.gpgsign false

mkdir -p src tests

cat > CLAUDE.md << 'MD'
# Test Project

## Entry Points

| Task | Start Here |
|------|------------|
| API | `src/api.ts` |
MD

cat > src/AGENTS.md << 'MD'
# Source

## Purpose
Application source.

## Entry Points

| Task | Start Here |
|------|------------|
| API | `src/api.ts` |
MD

cat > src/api.ts << 'TS'
export function listUsers() {
  return [];
}
TS

cat > tests/api.test.ts << 'TS'
import { listUsers } from "../src/api";

describe("listUsers", () => {
  it("returns an array", () => {
    expect(listUsers()).toEqual([]);
  });
});
TS

git add -A
git commit -q -m "initial commit"
git checkout -q -b feature/semantic-diff-test

cat > src/api.ts << 'TS'
export function listUsers() {
  return [];
}

export function createUser(name: string) {
  if (!name) {
    throw new Error("name required");
  }

  return { id: 1, name };
}
TS

cat > tests/api.test.ts << 'TS'
import { createUser, listUsers } from "../src/api";

describe("listUsers", () => {
  it("returns an array", () => {
    expect(listUsers()).toEqual([]);
  });
});

describe("createUser", () => {
  it("requires a name", () => {
    expect(() => createUser("")).toThrow("name required");
  });
});
TS

git add -A
git commit -q -m "add createUser"

echo "Test 3: No-change handling returns success"
status=0
output=$("$EXPLAIN" HEAD HEAD 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "No changed files detected"; then
    pass "No-change handling returns success"
else
    fail "Expected no-change success, got status=$status: $output"
fi

echo "Test 4: Dry-run shows affected node and scoped files"
status=0
output=$("$EXPLAIN" main HEAD --dry-run 2>&1) || status=$?

if [[ $status -eq 0 ]] && \
   echo "$output" | grep -q "Dry-run mode" && \
   echo "$output" | grep -q "src/AGENTS.md" && \
   echo "$output" | grep -q "src/api.ts"; then
    pass "Dry-run shows affected node and files"
else
    fail "Dry-run output missing expected content (status=$status): $output"
fi

echo "Test 5: Semantic explanation includes structured sections"
status=0
output=$(ANTHROPIC_API_KEY="" "$EXPLAIN" main HEAD 2>&1) || status=$?

if [[ $status -eq 0 ]] && \
   echo "$output" | grep -q "# Semantic Diff Explainer" && \
   echo "$output" | grep -q "## src/AGENTS.md" && \
   echo "$output" | grep -q "Behavioral impact:" && \
   echo "$output" | grep -q "Contract impact:" && \
   echo "$output" | grep -q "Review focus:"; then
    pass "Structured semantic explanation is emitted"
else
    fail "Semantic explanation formatting missing expected sections (status=$status): $output"
fi

echo "Test 6: Contract-like changes are called out"
status=0
output=$(ANTHROPIC_API_KEY="" "$EXPLAIN" main HEAD 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "Interfaces, invariants, or caller expectations likely changed"; then
    pass "Contract-like changes are surfaced"
else
    fail "Expected contract impact language, got status=$status: $output"
fi

git checkout -q main
git checkout -q -b feature/direct-node-only

cat > CLAUDE.md << 'MD'
# Test Project

## Entry Points

| Task | Start Here |
|------|------------|
| API | `src/api.ts` |

## Review Notes

- Root node guidance changed.
MD

git add CLAUDE.md
git commit -q -m "update root intent node"

echo "Test 7: Direct Intent-node-only changes produce a semantic explanation"
status=0
output=$(ANTHROPIC_API_KEY="" "$EXPLAIN" main HEAD 2>&1) || status=$?

if [[ $status -eq 0 ]] && \
   echo "$output" | grep -q "## Directly Modified Nodes" && \
   echo "$output" | grep -q -- "- CLAUDE.md" && \
   echo "$output" | grep -q "## CLAUDE.md" && \
   echo "$output" | grep -q "Behavioral impact:"; then
    pass "Direct Intent-node-only changes are explained"
else
    fail "Expected semantic explanation for direct node-only change, got status=$status: $output"
fi

echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[[ "$FAILED" -gt 0 ]] && exit 1
echo "All tests passed!"
