#!/usr/bin/env bash
# A test script with intentional contract violations

# VIOLATION 1: Missing `set -euo pipefail` (required by contract)

# VIOLATION 2: Hardcoded path instead of $TARGET_PATH variable
REPORT_DIR="/Users/someone/reports"

# VIOLATION 3: Missing --help support (required by contract)
# The script has no argument parsing at all

# Script logic
echo "Running test..."
if [ -d "$REPORT_DIR" ]; then
    ls "$REPORT_DIR"
fi
