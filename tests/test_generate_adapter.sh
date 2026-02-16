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
# Fixture: project with root CLAUDE.md + two child nodes
# ============================================================
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"

# Root node
cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

> **TL;DR**: A test project for adapter generation.

## Contracts

- All API calls must be authenticated
- Never log PII

## Pitfalls

- Config values are case-sensitive

## Entry Points

| Task | Start Here |
|------|------------|
| Run tests | `make test` |

## Patterns

### Error handling

Use Result types for all service boundaries.
EOF

# Child node: src/api/
mkdir -p "$TEST_DIR/src/api"
cat > "$TEST_DIR/src/api/AGENTS.md" << 'EOF'
# API Module

## Purpose
Owns: REST endpoints and request validation.

## Contracts
- All endpoints return JSON
- Rate limiting via Redis

## Pitfalls
- `validate()` silently passes on empty input
- Route order matters

## Entry Points
| Task | Start Here |
|------|------------|
| Add endpoint | `routes/` |

## Patterns
### Adding a new endpoint
1. Create route in `routes/`
2. Add validation middleware
3. Register in `index.ts`
EOF

# Child node: src/core/
mkdir -p "$TEST_DIR/src/core"
cat > "$TEST_DIR/src/core/AGENTS.md" << 'EOF'
# Core Module

## Purpose
Owns: Business logic and domain models.

## Contracts
- All domain operations are idempotent
- Use transaction IDs for retries
EOF

echo "=== generate_adapter.sh Tests ==="
echo ""

# ---- Test 1: --help flag works ----
echo "Test 1: --help flag works"
output=$("$PLUGIN_DIR/scripts/generate_adapter.sh" --help 2>&1 || true)
if echo "$output" | grep -q "generate_adapter.sh" && echo "$output" | grep -q "format"; then
    pass "--help shows usage with format info"
else
    fail "--help output missing expected content: $output"
fi

# ---- Test 2: cursor format produces valid .mdc files ----
echo "Test 2: cursor format produces valid .mdc files"
CURSOR_DIR="$TEST_DIR/.cursor/rules"
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format cursor 2>/dev/null

# Check root .mdc exists
if [[ -f "$CURSOR_DIR/intent-layer-root.mdc" ]]; then
    pass "Root .mdc file created"
else
    fail "Root .mdc file not found at $CURSOR_DIR/intent-layer-root.mdc"
fi

# Check child .mdc exists
if [[ -f "$CURSOR_DIR/intent-layer-src-api.mdc" ]]; then
    pass "Child .mdc file created for src/api"
else
    fail "Child .mdc for src/api not found"
fi

if [[ -f "$CURSOR_DIR/intent-layer-src-core.mdc" ]]; then
    pass "Child .mdc file created for src/core"
else
    fail "Child .mdc for src/core not found"
fi

# Check YAML frontmatter in root
if grep -q "^---" "$CURSOR_DIR/intent-layer-root.mdc" && \
   grep -q "alwaysApply: true" "$CURSOR_DIR/intent-layer-root.mdc"; then
    pass "Root .mdc has YAML frontmatter with alwaysApply: true"
else
    fail "Root .mdc missing frontmatter or alwaysApply"
fi

# Check YAML frontmatter in child
if grep -q "alwaysApply: false" "$CURSOR_DIR/intent-layer-src-api.mdc" && \
   grep -q 'globs:' "$CURSOR_DIR/intent-layer-src-api.mdc"; then
    pass "Child .mdc has alwaysApply: false and globs"
else
    fail "Child .mdc missing alwaysApply or globs"
fi

# Check globs value matches directory
if grep -q 'src/api/\*\*' "$CURSOR_DIR/intent-layer-src-api.mdc"; then
    pass "Child .mdc globs matches directory path"
else
    fail "Child .mdc globs doesn't match expected path"
fi

# Check content is present
if grep -q "All API calls must be authenticated" "$CURSOR_DIR/intent-layer-root.mdc"; then
    pass "Root .mdc contains node content"
else
    fail "Root .mdc missing node content"
fi

# ---- Test 3: raw format outputs merged markdown ----
echo "Test 3: raw format outputs merged markdown"
raw_output=$("$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format raw 2>/dev/null)

# Should contain root content
if echo "$raw_output" | grep -q "All API calls must be authenticated"; then
    pass "Raw output contains root content"
else
    fail "Raw output missing root content"
fi

# Should contain child content
if echo "$raw_output" | grep -q "Rate limiting via Redis"; then
    pass "Raw output contains child content"
else
    fail "Raw output missing child content"
fi

# Should contain source markers
if echo "$raw_output" | grep -q "Source: CLAUDE.md"; then
    pass "Raw output has source marker for root"
else
    fail "Raw output missing source marker"
fi

# ---- Test 4: Token budget drops sections when exceeded ----
echo "Test 4: Token budget drops sections when exceeded"

# Use a very small token budget to force section dropping
# 80% of 100 = 80 effective tokens = 320 bytes. The root CLAUDE.md is much larger.
drop_output=$("$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format raw --max-tokens 100 2>&1 >/dev/null || true)

if echo "$drop_output" | grep -q "Warning.*Dropped section"; then
    pass "Token budget triggers section drop warnings"
else
    fail "No section drop warning with tiny budget: $drop_output"
fi

# ---- Test 5: No Intent Layer → exit 2 ----
echo "Test 5: No Intent Layer returns exit 2"
EMPTY_DIR=$(mktemp -d)
exit_code=0
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$EMPTY_DIR" --format raw 2>/dev/null >/dev/null || exit_code=$?
rm -rf "$EMPTY_DIR"

if [[ "$exit_code" -eq 2 ]]; then
    pass "Exit 2 when no Intent Layer found"
else
    fail "Expected exit 2, got $exit_code"
fi

# ---- Test 6: Idempotent (running twice produces same output; stale files cleaned) ----
echo "Test 6: Idempotent — stale .mdc files cleaned"

# First run already happened in test 2. Create a stale .mdc file.
touch "$CURSOR_DIR/intent-layer-old-module.mdc"

# Verify the stale file exists
if [[ -f "$CURSOR_DIR/intent-layer-old-module.mdc" ]]; then
    pass "Stale .mdc file created for test"
else
    fail "Could not create stale .mdc file"
fi

# Run again
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format cursor 2>/dev/null

# Stale file should be removed
if [[ ! -f "$CURSOR_DIR/intent-layer-old-module.mdc" ]]; then
    pass "Stale .mdc file removed on re-run"
else
    fail "Stale .mdc file still present after re-run"
fi

# Valid files should still exist
if [[ -f "$CURSOR_DIR/intent-layer-root.mdc" ]] && \
   [[ -f "$CURSOR_DIR/intent-layer-src-api.mdc" ]] && \
   [[ -f "$CURSOR_DIR/intent-layer-src-core.mdc" ]]; then
    pass "Valid .mdc files preserved on re-run"
else
    fail "Valid .mdc files missing after re-run"
fi

# Content should be identical between runs
first_content=$(cat "$CURSOR_DIR/intent-layer-root.mdc")
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format cursor 2>/dev/null
second_content=$(cat "$CURSOR_DIR/intent-layer-root.mdc")

if [[ "$first_content" == "$second_content" ]]; then
    pass "Content identical between runs (idempotent)"
else
    fail "Content differs between runs"
fi

# ---- Test 7: Root-only project (no child nodes) ----
echo "Test 7: Root-only project (no child nodes)"
ROOT_ONLY_DIR=$(mktemp -d)
cat > "$ROOT_ONLY_DIR/CLAUDE.md" << 'EOF'
# Root Only Project

## Contracts

- Single file project
EOF

ROOT_ONLY_OUT="$ROOT_ONLY_DIR/.cursor/rules"
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$ROOT_ONLY_DIR" --format cursor 2>/dev/null

if [[ -f "$ROOT_ONLY_OUT/intent-layer-root.mdc" ]]; then
    pass "Root-only project generates root .mdc"
else
    fail "Root-only project missing root .mdc"
fi

# Should be exactly 1 .mdc file
mdc_count=$(find "$ROOT_ONLY_OUT" -name "*.mdc" -type f | wc -l | tr -d ' ')
if [[ "$mdc_count" -eq 1 ]]; then
    pass "Root-only project produces exactly 1 .mdc file"
else
    fail "Root-only project produced $mdc_count .mdc files (expected 1)"
fi

# Raw format should also work
raw_root_only=$("$PLUGIN_DIR/scripts/generate_adapter.sh" "$ROOT_ONLY_DIR" --format raw 2>/dev/null)
if echo "$raw_root_only" | grep -q "Single file project"; then
    pass "Raw format works for root-only project"
else
    fail "Raw format missing content for root-only project"
fi

rm -rf "$ROOT_ONLY_DIR"

# ---- Test 8: --output flag for raw format ----
echo "Test 8: --output flag writes to file"
RAW_OUT="$TEST_DIR/adapter-output.md"
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format raw --output "$RAW_OUT" 2>/dev/null

if [[ -f "$RAW_OUT" ]]; then
    pass "--output creates file"
else
    fail "--output did not create file"
fi

if grep -q "All API calls must be authenticated" "$RAW_OUT"; then
    pass "--output file contains expected content"
else
    fail "--output file missing expected content"
fi

# ---- Test 9: --output flag for cursor format ----
echo "Test 9: --output flag for cursor writes to custom directory"
CUSTOM_CURSOR_DIR="$TEST_DIR/custom-rules"
"$PLUGIN_DIR/scripts/generate_adapter.sh" "$TEST_DIR" --format cursor --output "$CUSTOM_CURSOR_DIR" 2>/dev/null

if [[ -f "$CUSTOM_CURSOR_DIR/intent-layer-root.mdc" ]]; then
    pass "Cursor --output writes to custom directory"
else
    fail "Cursor --output did not write to custom directory"
fi

# ---- Test 10: Missing project root → exit 1 ----
echo "Test 10: Missing project root returns exit 1"
exit_code=0
"$PLUGIN_DIR/scripts/generate_adapter.sh" "/nonexistent/path" 2>/dev/null >/dev/null || exit_code=$?

if [[ "$exit_code" -eq 1 ]]; then
    pass "Exit 1 for missing project root"
else
    fail "Expected exit 1, got $exit_code"
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
