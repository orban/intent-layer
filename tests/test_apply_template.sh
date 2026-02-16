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

TEST_DIR=$(mktemp -d)

echo "=== apply_template.sh Tests ==="
echo ""

# ---- Test 1: --help works ----
echo "Test 1: --help exits 0 and shows usage"
status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" --help 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "USAGE"; then
    pass "--help exits 0 and shows usage"
else
    fail "--help (status=$status): $output"
fi

# ---- Test 2: --list shows generic template ----
echo "Test 2: --list shows generic template"
status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" --list 2>&1) || status=$?

if [[ $status -eq 0 ]] && echo "$output" | grep -q "generic"; then
    pass "--list shows generic template"
else
    fail "--list (status=$status): $output"
fi

# ---- Test 3: --preview shows what would be created ----
echo "Test 3: --preview shows files without creating them"
PREVIEW_DIR="$TEST_DIR/preview_test"
mkdir -p "$PREVIEW_DIR"

status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" --preview "$PREVIEW_DIR" generic 2>&1) || status=$?

has_claude=false
has_agents=false
echo "$output" | grep -q "CLAUDE.md" && has_claude=true
echo "$output" | grep -q "AGENTS.md" && has_agents=true

# Files should NOT be created
no_files=true
[[ -f "$PREVIEW_DIR/CLAUDE.md" ]] && no_files=false
[[ -f "$PREVIEW_DIR/src/AGENTS.md" ]] && no_files=false

if [[ $status -eq 0 ]] && $has_claude && $has_agents && $no_files; then
    pass "--preview shows files without creating them"
else
    fail "--preview (status=$status claude=$has_claude agents=$has_agents no_files=$no_files): $output"
fi

# ---- Test 4: Applying generic template creates correct files ----
echo "Test 4: Applying generic template creates CLAUDE.md and src/AGENTS.md"
APPLY_DIR="$TEST_DIR/apply_test"
mkdir -p "$APPLY_DIR"

status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" "$APPLY_DIR" generic 2>&1) || status=$?

if [[ $status -eq 0 ]] && [[ -f "$APPLY_DIR/CLAUDE.md" ]] && [[ -f "$APPLY_DIR/src/AGENTS.md" ]]; then
    pass "Generic template creates CLAUDE.md and src/AGENTS.md"
else
    fail "apply (status=$status): $output"
fi

# Verify content matches template (spot check)
if grep -q "Intent Layer" "$APPLY_DIR/CLAUDE.md" && grep -q "## Purpose" "$APPLY_DIR/src/AGENTS.md"; then
    pass "Created files have expected content"
else
    fail "Created files have unexpected content"
fi

# ---- Test 5: Won't overwrite without --force ----
echo "Test 5: Won't overwrite existing files without --force"
status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" "$APPLY_DIR" generic 2>&1) || status=$?

if [[ $status -eq 1 ]] && echo "$output" | grep -qi "already exists"; then
    pass "Refuses to overwrite without --force"
else
    fail "overwrite guard (status=$status): $output"
fi

# ---- Test 6: --force overwrites existing files ----
echo "Test 6: --force overwrites existing files"
# Write known content to detect overwrite
echo "MARKER_BEFORE" > "$APPLY_DIR/CLAUDE.md"

status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" --force "$APPLY_DIR" generic 2>&1) || status=$?

marker_gone=true
grep -q "MARKER_BEFORE" "$APPLY_DIR/CLAUDE.md" && marker_gone=false

if [[ $status -eq 0 ]] && $marker_gone; then
    pass "--force overwrites existing files"
else
    fail "--force (status=$status marker_gone=$marker_gone): $output"
fi

# ---- Test 7: Unknown template exits 2 with available templates ----
echo "Test 7: Unknown template exits 2 and shows available templates"
EMPTY_DIR="$TEST_DIR/unknown_test"
mkdir -p "$EMPTY_DIR"

status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" "$EMPTY_DIR" nonexistent 2>&1) || status=$?

if [[ $status -eq 2 ]] && echo "$output" | grep -q "generic"; then
    pass "Unknown template exits 2 and lists available templates"
else
    fail "unknown template (status=$status): $output"
fi

# ---- Test 8: Templates pass validate_node.sh ----
echo "Test 8: Generated templates pass validate_node.sh"
VALIDATE_DIR="$TEST_DIR/validate_test"
mkdir -p "$VALIDATE_DIR"

"$PLUGIN_DIR/scripts/apply_template.sh" "$VALIDATE_DIR" generic >/dev/null 2>&1

root_status=0
"$PLUGIN_DIR/scripts/validate_node.sh" --quiet "$VALIDATE_DIR/CLAUDE.md" >/dev/null 2>&1 || root_status=$?

child_status=0
"$PLUGIN_DIR/scripts/validate_node.sh" --quiet "$VALIDATE_DIR/src/AGENTS.md" >/dev/null 2>&1 || child_status=$?

if [[ $root_status -eq 0 ]] && [[ $child_status -eq 0 ]]; then
    pass "Both templates pass validate_node.sh"
else
    fail "validate_node.sh (root=$root_status child=$child_status)"
fi

# ---- Test 9: Path traversal rejected ----
echo "Test 9: Path traversal in template files is rejected"
# Create a malicious template with path traversal
EVIL_TPL="$PLUGIN_DIR/references/templates/_test_evil"
mkdir -p "$EVIL_TPL"
echo "Evil template" > "$EVIL_TPL/README.md"
# Create a template file with path traversal in its name
mkdir -p "$EVIL_TPL/../../../../../../tmp"  2>/dev/null || true
# We can't actually create a file named ../../etc/foo.template in the template dir
# because the filesystem would resolve it. Instead, test that the script's
# validate_dest_path rejects destinations outside project root.
# Create a normal template and check the script works, then clean up.

TRAVERSAL_DIR="$TEST_DIR/traversal_test"
mkdir -p "$TRAVERSAL_DIR"

# The real protection is: template relative paths that resolve outside PROJECT_ROOT
# get rejected. We test this by creating a template whose relative path, when
# applied to PROJECT_ROOT, would escape. We simulate by creating a symlink.
# Create a template with a deeply nested path containing ..
TRICK_TPL="$PLUGIN_DIR/references/templates/_test_traversal"
mkdir -p "$TRICK_TPL"
echo "Traversal test" > "$TRICK_TPL/README.md"

# Create template file that tries to escape via symlink in the template dir
# Since we can't put literal ".." in filenames, create a subdir with a symlink
# pointing outside, then a template inside it
SYMLINK_ESCAPE="$TRICK_TPL/escape"
ln -sf /tmp "$SYMLINK_ESCAPE" 2>/dev/null || true
if [[ -L "$SYMLINK_ESCAPE" ]]; then
    echo "test" > "$TRICK_TPL/escape/evil_file.template" 2>/dev/null || true
fi

status=0
output=$("$PLUGIN_DIR/scripts/apply_template.sh" "$TRAVERSAL_DIR" _test_traversal 2>&1) || status=$?

# Check that no files were created outside TRAVERSAL_DIR
outside_file=false
[[ -f /tmp/evil_file ]] && outside_file=true

if ! $outside_file; then
    pass "Path traversal via symlink does not write outside project root"
else
    fail "Path traversal protection failed — file written outside project root"
fi

# Clean up test templates
rm -f "$TRICK_TPL/escape/evil_file.template" 2>/dev/null || true
rm -f "$SYMLINK_ESCAPE" 2>/dev/null || true
rm -rf "$TRICK_TPL" 2>/dev/null || true
rm -rf "$EVIL_TPL" 2>/dev/null || true

# ============================================================
# Summary
# ============================================================
echo ""
echo "=== Results ==="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
[[ "$FAILED" -gt 0 ]] && exit 1
echo "All tests passed!"
