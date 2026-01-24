#!/usr/bin/env bash
# End-to-end test for the learning layer
# Tests the full flow: failure → skeleton → review → integration → cleanup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
TEST_DIR=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    FAILED=$((FAILED + 1))
}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

step() {
    echo ""
    echo -e "${YELLOW}━━━ $1 ━━━${NC}"
}

cleanup() {
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        info "Cleaning up test directory: $TEST_DIR"
        rm -rf "$TEST_DIR"
    fi
}

trap cleanup EXIT

# =============================================================================
# SETUP
# =============================================================================

step "Setting up test environment"

# Create isolated test directory
TEST_DIR=$(mktemp -d)
info "Test directory: $TEST_DIR"

# Set environment variables
export CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR"
export CLAUDE_PROJECT_DIR="$TEST_DIR"

# Create a test project structure with AGENTS.md
mkdir -p "$TEST_DIR/src/api"
cat > "$TEST_DIR/AGENTS.md" << 'EOF'
# Test Project

This is a test project for e2e testing.

## Overview

A simple test project.

## Pitfalls

<!-- Pitfalls will be added here -->

EOF

cat > "$TEST_DIR/src/api/AGENTS.md" << 'EOF'
# API Module

Handles API requests.

## Pitfalls

<!-- API-specific pitfalls -->

EOF

info "Created test project structure:"
find "$TEST_DIR" -name "*.md" | while read f; do echo "  - ${f#$TEST_DIR/}"; done

# =============================================================================
# TEST 1: Tool Failure → Skeleton Auto-Creation
# =============================================================================

step "Test 1: Tool failure triggers skeleton auto-creation"

# Simulate an Edit tool failure on a file in src/api
FAILURE_INPUT=$(cat << EOF
{
    "hook_event_name": "PostToolUseFailure",
    "tool_name": "Edit",
    "tool_input": {
        "file_path": "$TEST_DIR/src/api/handlers.ts",
        "old_string": "function handleRequest",
        "new_string": "async function handleRequest"
    },
    "tool_error": "old_string not found in file"
}
EOF
)

cd "$TEST_DIR"
output=$(echo "$FAILURE_INPUT" | "$PLUGIN_DIR/scripts/capture-tool-failure.sh" 2>&1 || true)

# Check skeleton was created
PENDING_DIR="$TEST_DIR/.intent-layer/mistakes/pending"
if [[ -d "$PENDING_DIR" ]] && ls "$PENDING_DIR"/SKELETON-*.md 1>/dev/null 2>&1; then
    SKELETON_FILE=$(ls -1 "$PENDING_DIR"/SKELETON-*.md | head -1)
    pass "Skeleton created: $(basename "$SKELETON_FILE")"

    # Verify skeleton content (check for Edit tool and directory)
    if grep -q "Edit" "$SKELETON_FILE" && \
       grep -q "handlers.ts" "$SKELETON_FILE" && \
       grep -q "Directory" "$SKELETON_FILE"; then
        pass "Skeleton contains expected fields"
    else
        fail "Skeleton missing expected fields"
        cat "$SKELETON_FILE"
    fi
else
    fail "No skeleton created in $PENDING_DIR"
    echo "Output was: $output"
fi

# =============================================================================
# TEST 2: SessionStart Detects Pending Skeletons
# =============================================================================

step "Test 2: SessionStart hook detects pending skeleton"

cd "$TEST_DIR"
session_output=$("$PLUGIN_DIR/scripts/inject-learnings.sh" < /dev/null 2>&1 || true)

if echo "$session_output" | grep -q "pending report"; then
    pass "SessionStart detects pending reports"
else
    fail "SessionStart should mention pending reports"
    echo "Output was: $session_output"
fi

if echo "$session_output" | grep -q "SKELETON-"; then
    pass "SessionStart lists skeleton file"
else
    fail "SessionStart should list the skeleton file"
fi

# =============================================================================
# TEST 3: Enrich Skeleton → Full Mistake Report
# =============================================================================

step "Test 3: Create enriched mistake report"

# Create a proper mistake report (simulating what the agent would do)
MISTAKE_ID="MISTAKE-$(date +%Y-%m-%d)-$(printf '%04d' $RANDOM)"
MISTAKE_FILE="$PENDING_DIR/$MISTAKE_ID.md"

cat > "$MISTAKE_FILE" << EOF
## Mistake Report
**ID**: $MISTAKE_ID
**Status**: pending
**Timestamp**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
**Session**: test-session-123

### Context
**Directory**: $TEST_DIR/src/api
**Operation**: Edit handlers.ts to make function async
**File**: $TEST_DIR/src/api/handlers.ts

### What Happened
Attempted to change "function handleRequest" to "async function handleRequest" but the old_string was not found.
The file uses arrow functions instead of traditional function declarations.

### Root Cause
The API handlers use arrow function syntax: \`const handleRequest = () => {}\` instead of \`function handleRequest() {}\`.

### Suggested Fix
Check the actual syntax in API files before attempting edits. Use \`Read\` tool first to verify function declaration style.

### Checklist
- [x] Captured at time of failure
- [ ] Reviewed by user
- [ ] Pitfall added to AGENTS.md
EOF

if [[ -f "$MISTAKE_FILE" ]]; then
    pass "Created enriched mistake report: $MISTAKE_ID"
else
    fail "Failed to create mistake report"
fi

# Remove the skeleton since we have a full report now
rm -f "$SKELETON_FILE" 2>/dev/null || true
info "Removed skeleton (replaced with full report)"

# =============================================================================
# TEST 4: Integration → Pitfall Added to AGENTS.md
# =============================================================================

step "Test 4: Integrate pitfall into covering AGENTS.md"

# Run the integration script
cd "$TEST_DIR"
integration_output=$("$PLUGIN_DIR/lib/integrate_pitfall.sh" "$MISTAKE_FILE" 2>&1 || true)

echo "$integration_output"

# Check if pitfall was added to the covering AGENTS.md (src/api/AGENTS.md)
COVERING_AGENTS="$TEST_DIR/src/api/AGENTS.md"
if grep -q "Edit handlerstts to make function async\|handleRequest\|arrow function" "$COVERING_AGENTS" 2>/dev/null; then
    pass "Pitfall added to covering AGENTS.md"
else
    # Check root AGENTS.md as fallback
    if grep -q "Edit handlerstts to make function async\|handleRequest\|arrow function" "$TEST_DIR/AGENTS.md" 2>/dev/null; then
        pass "Pitfall added to root AGENTS.md"
    else
        fail "Pitfall not found in any AGENTS.md"
        echo "--- src/api/AGENTS.md ---"
        cat "$COVERING_AGENTS"
        echo "--- root AGENTS.md ---"
        cat "$TEST_DIR/AGENTS.md"
    fi
fi

# =============================================================================
# TEST 5: Cleanup → Mistake Moved to Integrated
# =============================================================================

step "Test 5: Mistake file moved to integrated/"

INTEGRATED_DIR="$TEST_DIR/.intent-layer/mistakes/integrated"
if [[ -d "$INTEGRATED_DIR" ]] && ls "$INTEGRATED_DIR"/*.md 1>/dev/null 2>&1; then
    pass "Mistake moved to integrated/"
    info "Integrated files:"
    ls -la "$INTEGRATED_DIR"
else
    fail "Mistake not moved to integrated/"
fi

# Verify pending is now empty (or only has the original skeleton backup)
PENDING_COUNT=$(find "$PENDING_DIR" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$PENDING_COUNT" -eq 0 ]]; then
    pass "Pending directory is empty"
else
    info "Note: $PENDING_COUNT files still in pending (may be expected)"
fi

# =============================================================================
# TEST 6: Verify Final AGENTS.md State
# =============================================================================

step "Test 6: Verify final AGENTS.md content"

echo ""
info "Final state of src/api/AGENTS.md:"
echo "─────────────────────────────────"
cat "$COVERING_AGENTS"
echo "─────────────────────────────────"

if grep -q "_Source: MISTAKE-" "$COVERING_AGENTS" 2>/dev/null || \
   grep -q "_Source: MISTAKE-" "$TEST_DIR/AGENTS.md" 2>/dev/null; then
    pass "Pitfall includes source reference"
else
    fail "Pitfall should include source reference"
fi

# =============================================================================
# SUMMARY
# =============================================================================

echo ""
echo "═══════════════════════════════════════════════════"
echo -e "           ${BLUE}E2E Test Results${NC}"
echo "═══════════════════════════════════════════════════"
echo -e "  ${GREEN}Passed${NC}: $PASSED"
echo -e "  ${RED}Failed${NC}: $FAILED"
echo "═══════════════════════════════════════════════════"

if [[ "$FAILED" -gt 0 ]]; then
    echo ""
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo ""
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
