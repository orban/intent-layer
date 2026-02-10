#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

PASSED=0
FAILED=0

pass() { echo "PASS: $1"; PASSED=$((PASSED + 1)); }
fail() { echo "FAIL: $1"; FAILED=$((FAILED + 1)); }

if ! command -v jq &>/dev/null; then
    echo "jq is required for this test"
    exit 1
fi

TEMP_PROJECT=$(mktemp -d)
trap 'rm -rf "$TEMP_PROJECT"' EXIT

cat > "$TEMP_PROJECT/AGENTS.md" << 'MD'
# Test Project

## Pitfalls
- Avoid rate limit spikes.
MD

output=$("$PLUGIN_DIR/scripts/query_intent.sh" "$TEMP_PROJECT" "rate" --section Pitfalls --json 2>/dev/null || true)

if echo "$output" | jq -e 'length >= 1' >/dev/null 2>&1 && \
   echo "$output" | jq -e '.[0].node == "AGENTS.md"' >/dev/null 2>&1; then
    pass "query_intent.sh --json outputs valid JSON"
else
    fail "query_intent.sh --json output invalid: $output"
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
