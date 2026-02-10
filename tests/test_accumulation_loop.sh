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

# Find most recent pending report by type prefix
find_latest_report() {
    ls -1t "$TEST_DIR/.intent-layer/mistakes/pending/${1}-"*.md 2>/dev/null | head -1
}

# Count ### entries in a section of a file
count_section_entries() {
    awk -v section="$2" '/^## /{ if(in_s) exit; if($0=="## "section) in_s=1 } in_s && /^### /{ c++ } END{ print c+0 }' "$1"
}

# ============================================================
# Fixture: project with root, child (api), and sibling (core)
# ============================================================
TEST_DIR=$(mktemp -d)
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# Root node
cat > "$TEST_DIR/CLAUDE.md" << 'EOF'
# Test Project

## Contracts

- All API calls must be authenticated
- Never log PII

## Pitfalls

### Config values are case-sensitive

Always use lowercase keys when reading from config.
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

echo "=== Accumulation Loop Tests ==="
echo ""

# ---- Test 1: Closure ----
echo "Test 1: Capture → Integrate → Resolve (full loop closure)"
"$PLUGIN_DIR/scripts/report_learning.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pitfall \
    --title "Null check on empty collections" \
    --detail "API returns null instead of empty array for collections with no results" \
    >/dev/null 2>&1 || true

REPORT=$(find_latest_report "PITFALL")
if [[ -z "$REPORT" ]]; then
    fail "No report created"
else
    "$PLUGIN_DIR/lib/integrate_pitfall.sh" --force "$REPORT" >/dev/null 2>&1 || true

    CONTEXT=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" 2>/dev/null)
    if echo "$CONTEXT" | grep -q "Null check on empty collections"; then
        pass "Learning flows capture → integration → context resolution"
    else
        fail "Integrated learning not found in resolved context"
    fi
fi

# ---- Test 2: Specificity ----
echo "Test 2: Sibling isolation (api pitfall NOT in core context)"
CORE_CONTEXT=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/core/" 2>/dev/null)

api_leak=false
core_own=false
echo "$CORE_CONTEXT" | grep -q "Null check on empty collections" && api_leak=true
echo "$CORE_CONTEXT" | grep -q "Engine retry logic" && core_own=true

if ! $api_leak && $core_own; then
    pass "API pitfall absent from core context; core's own pitfall present"
else
    fail "api_leak=$api_leak core_own=$core_own"
fi

# ---- Test 3: Accumulation ----
echo "Test 3: Multiple learnings coexist after accumulation"
"$PLUGIN_DIR/scripts/report_learning.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pitfall \
    --title "Rate limiter ignores OPTIONS requests" \
    --detail "CORS preflight passes through rate limiter without decrementing quota" \
    >/dev/null 2>&1 || true

REPORT2=$(find_latest_report "PITFALL")
if [[ -z "$REPORT2" ]]; then
    fail "Second report not created"
else
    "$PLUGIN_DIR/lib/integrate_pitfall.sh" --force "$REPORT2" >/dev/null 2>&1 || true

    CONTEXT=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" 2>/dev/null)
    has_original=false
    has_first=false
    has_second=false
    echo "$CONTEXT" | grep -q "validate.*silently passes" && has_original=true
    echo "$CONTEXT" | grep -q "Null check on empty collections" && has_first=true
    echo "$CONTEXT" | grep -q "Rate limiter ignores OPTIONS" && has_second=true

    if $has_original && $has_first && $has_second; then
        pass "Pre-populated + 2 captured pitfalls all coexist in resolved context"
    else
        fail "original=$has_original first=$has_first second=$has_second"
    fi
fi

# ---- Test 4: Consumption (PreToolUse hook) ----
echo "Test 4: PreToolUse hook injects integrated learnings"
HOOK_INPUT='{"tool_name":"Edit","tool_input":{"file_path":"'"$TEST_DIR/src/api/handlers.ts"'"}}'
HOOK_OUTPUT=$(echo "$HOOK_INPUT" | "$PLUGIN_DIR/scripts/pre-edit-check.sh" 2>/dev/null || true)

if echo "$HOOK_OUTPUT" | grep -q "Null check on empty collections" && \
   echo "$HOOK_OUTPUT" | grep -q "Rate limiter ignores OPTIONS"; then
    pass "PreToolUse hook output contains integrated learnings"
else
    fail "Hook output missing learnings"
fi

# ---- Test 5: Deduplication ----
echo "Test 5: Near-duplicate detected and blocked"
"$PLUGIN_DIR/scripts/report_learning.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pitfall \
    --title "Null check on empty collections issue" \
    --detail "Duplicate of earlier finding about null returns" \
    >/dev/null 2>&1 || true

DUP_REPORT=$(find_latest_report "PITFALL")
if [[ -z "$DUP_REPORT" ]]; then
    fail "Duplicate report not created"
else
    EXIT_CODE=0
    "$PLUGIN_DIR/lib/integrate_pitfall.sh" --check-only "$DUP_REPORT" >/dev/null 2>&1 || EXIT_CODE=$?

    if [[ "$EXIT_CODE" -eq 2 ]]; then
        pass "Duplicate detected (exit code 2 from --check-only)"
    else
        fail "Expected exit code 2, got $EXIT_CODE"
    fi
fi

# ---- Test 6: Type mapping ----
echo "Test 6: Learning types map to correct AGENTS.md sections"

# Capture + integrate a check
"$PLUGIN_DIR/scripts/report_learning.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type check \
    --title "Verify auth middleware" \
    --detail "Run auth test suite before modifying middleware chain" \
    >/dev/null 2>&1 || true

CHECK_REPORT=$(find_latest_report "CHECK")
[[ -n "$CHECK_REPORT" ]] && \
    "$PLUGIN_DIR/lib/integrate_pitfall.sh" --force "$CHECK_REPORT" >/dev/null 2>&1 || true

# Capture + integrate a pattern
"$PLUGIN_DIR/scripts/report_learning.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type pattern \
    --title "Use middleware composition" \
    --detail "Compose handlers with pipe rather than nesting callbacks" \
    >/dev/null 2>&1 || true

PATTERN_REPORT=$(find_latest_report "PATTERN")
[[ -n "$PATTERN_REPORT" ]] && \
    "$PLUGIN_DIR/lib/integrate_pitfall.sh" --force "$PATTERN_REPORT" >/dev/null 2>&1 || true

# Capture + integrate an insight
"$PLUGIN_DIR/scripts/report_learning.sh" \
    --project "$TEST_DIR" \
    --path "src/api/handlers.ts" \
    --type insight \
    --title "Request validation runs twice" \
    --detail "Both middleware and handler validate - intentional defense in depth" \
    >/dev/null 2>&1 || true

INSIGHT_REPORT=$(find_latest_report "INSIGHT")
[[ -n "$INSIGHT_REPORT" ]] && \
    "$PLUGIN_DIR/lib/integrate_pitfall.sh" --force "$INSIGHT_REPORT" >/dev/null 2>&1 || true

# Verify sections exist in the AGENTS.md file
AGENTS="$TEST_DIR/src/api/AGENTS.md"
missing_sections=""
grep -q "^## Checks" "$AGENTS" || missing_sections="$missing_sections Checks"
grep -q "^## Patterns" "$AGENTS" || missing_sections="$missing_sections Patterns"
grep -q "^## Context" "$AGENTS" || missing_sections="$missing_sections Context"

if [[ -z "$missing_sections" ]]; then
    # Also verify all 4 section types visible via resolve_context.sh
    CONTEXT=$("$PLUGIN_DIR/scripts/resolve_context.sh" "$TEST_DIR" "src/api/" 2>/dev/null)
    has_all=true
    echo "$CONTEXT" | grep -q "## Pitfalls" || has_all=false
    echo "$CONTEXT" | grep -q "## Checks" || has_all=false
    echo "$CONTEXT" | grep -q "## Patterns" || has_all=false
    echo "$CONTEXT" | grep -q "## Context" || has_all=false

    if $has_all; then
        pass "All 4 section types (Pitfalls, Checks, Patterns, Context) present in resolved context"
    else
        fail "Sections exist in file but not all present in resolved context"
    fi
else
    fail "Missing sections in AGENTS.md:$missing_sections"
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
