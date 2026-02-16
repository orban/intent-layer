#!/usr/bin/env bash
# show_telemetry.sh - Context telemetry dashboard
#
# Joins injections.log and outcomes.log to show whether AGENTS.md
# injections correlate with edit success/failure.
#
# Usage: show_telemetry.sh [project_root] [-h|--help]
#
# Exit codes:
#   0 - Success
#   1 - Bad arguments
#   2 - No telemetry data

set -euo pipefail

show_help() {
    cat << 'EOF'
show_telemetry.sh - Intent Layer context telemetry dashboard

USAGE:
    show_telemetry.sh [OPTIONS] [PROJECT_ROOT]

ARGUMENTS:
    PROJECT_ROOT    Project directory (default: current directory)

OPTIONS:
    -h, --help    Show this help message

OUTPUT:
    Dashboard showing:
    - Per-node success/failure rates (which AGENTS.md nodes correlate best)
    - Coverage gaps (files edited without any AGENTS.md injection)
    - Summary stats and daily trend

DATA SOURCES:
    .intent-layer/hooks/injections.log   (written by pre-edit-check.sh)
    .intent-layer/hooks/outcomes.log     (written by post-edit-check.sh, capture-tool-failure.sh)

OPT-OUT:
    Touch .intent-layer/disable-telemetry to stop collecting outcome data.

EXAMPLES:
    show_telemetry.sh                    # Dashboard for current project
    show_telemetry.sh /path/to/project   # Dashboard for specific project
EOF
    exit 0
}

# Parse arguments
TARGET_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "   Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [[ -n "$TARGET_PATH" ]]; then
                echo "Error: Multiple paths specified" >&2
                exit 1
            fi
            TARGET_PATH="$1"
            shift
            ;;
    esac
done

TARGET_PATH="${TARGET_PATH:-.}"

if [[ ! -d "$TARGET_PATH" ]]; then
    echo "Error: Directory not found: $TARGET_PATH" >&2
    exit 1
fi

# Resolve to absolute path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

INJECTIONS_LOG="$TARGET_PATH/.intent-layer/hooks/injections.log"
OUTCOMES_LOG="$TARGET_PATH/.intent-layer/hooks/outcomes.log"

# Check for data
if [[ ! -f "$OUTCOMES_LOG" ]] || [[ ! -s "$OUTCOMES_LOG" ]]; then
    echo "No telemetry data. Edits are logged automatically — check back after a coding session."
    exit 2
fi

# Read outcomes into temp files for processing
TMPDIR_WORK=$(mktemp -d)
trap 'rm -rf "$TMPDIR_WORK"' EXIT

cp "$OUTCOMES_LOG" "$TMPDIR_WORK/outcomes.tsv"

# Copy injections if available
if [[ -f "$INJECTIONS_LOG" && -s "$INJECTIONS_LOG" ]]; then
    cp "$INJECTIONS_LOG" "$TMPDIR_WORK/injections.tsv"
else
    touch "$TMPDIR_WORK/injections.tsv"
fi

# === Summary stats ===

TOTAL_EDITS=$(wc -l < "$TMPDIR_WORK/outcomes.tsv" | tr -d ' ')
SUCCESS_EDITS=$(awk -F'\t' '$3 == "success"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')
FAILURE_EDITS=$(awk -F'\t' '$3 == "failure"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')

# === Join: match outcomes to injections ===
# For each outcome line, find an injection with the same file path
# and timestamp within 1 second (injection happens right before the edit).
#
# Strategy: convert timestamps to epoch seconds, compare.
# We build a lookup from injections keyed by file path, then scan outcomes.

# Join outcomes to injections entirely in awk (avoids shelling out to date per line).
# Converts ISO 8601 timestamps to approximate seconds for comparison.
# The approximation (365-day year, 30-day month) is fine since we only compare
# timestamps within seconds of each other.

awk -F'\t' '
function iso_to_secs(ts,    parts, dp, tp) {
    # Input: 2026-02-15T10:30:00Z → approximate seconds
    split(ts, parts, "T")
    split(parts[1], dp, "-")
    gsub(/Z$/, "", parts[2])
    split(parts[2], tp, ":")
    return ((dp[1] * 365 + dp[2] * 30 + dp[3]) * 86400) + tp[1] * 3600 + tp[2] * 60 + tp[3]
}

# Pass 1: load injections (file 1)
NR == FNR {
    inj_epoch[NR] = iso_to_secs($1)
    inj_file[NR] = $2
    inj_node[NR] = $3
    inj_count = NR
    next
}

# Pass 2: process outcomes (file 2)
{
    o_epoch = iso_to_secs($1)
    o_result = $3
    o_file = $4
    matched = "UNCOVERED"
    for (i = 1; i <= inj_count; i++) {
        if (inj_file[i] == o_file) {
            diff = o_epoch - inj_epoch[i]
            # Injection happens 0-5 seconds before the outcome
            if (diff >= 0 && diff <= 5) {
                matched = inj_node[i]
                break
            }
        }
    }
    printf "%s\t%s\t%s\n", o_result, matched, o_file
}
' "$TMPDIR_WORK/injections.tsv" "$TMPDIR_WORK/outcomes.tsv" > "$TMPDIR_WORK/joined.tsv"

# === Compute metrics ===

COVERED_EDITS=$(awk -F'\t' '$2 != "UNCOVERED"' "$TMPDIR_WORK/joined.tsv" | wc -l | tr -d ' ')
UNCOVERED_EDITS=$(awk -F'\t' '$2 == "UNCOVERED"' "$TMPDIR_WORK/joined.tsv" | wc -l | tr -d ' ')

if [[ "$TOTAL_EDITS" -gt 0 ]]; then
    COVERED_PCT=$(( COVERED_EDITS * 100 / TOTAL_EDITS ))
    UNCOVERED_PCT=$(( UNCOVERED_EDITS * 100 / TOTAL_EDITS ))
    SUCCESS_RATE=$(( SUCCESS_EDITS * 100 / TOTAL_EDITS ))
else
    COVERED_PCT=0
    UNCOVERED_PCT=0
    SUCCESS_RATE=0
fi

# Date range (sorted chronologically, not by line order)
FIRST_DATE=$(awk -F'\t' '{split($1,a,"T"); print a[1]}' "$TMPDIR_WORK/outcomes.tsv" | sort | head -1)
LAST_DATE=$(awk -F'\t' '{split($1,a,"T"); print a[1]}' "$TMPDIR_WORK/outcomes.tsv" | sort | tail -1)

# === Per-node success rates ===
# From joined.tsv: result \t node \t file
# Group by node (excluding UNCOVERED), count success/total

awk -F'\t' '$2 != "UNCOVERED" {
    node = $2
    total[node]++
    if ($1 == "success") success[node]++
}
END {
    for (node in total) {
        s = (node in success) ? success[node] : 0
        if (total[node] > 0)
            rate = int(s * 100 / total[node])
        else
            rate = 0
        printf "%s\t%d\t%d\t%d\n", node, total[node], s, rate
    }
}' "$TMPDIR_WORK/joined.tsv" | sort -t$'\t' -k2 -rn > "$TMPDIR_WORK/per_node.tsv"

# === Coverage gaps ===
# Files edited without AGENTS.md context, grouped by file

awk -F'\t' '$2 == "UNCOVERED" {
    files[$3]++
}
END {
    for (f in files) {
        printf "%s\t%d\n", f, files[f]
    }
}' "$TMPDIR_WORK/joined.tsv" | sort -t$'\t' -k2 -rn > "$TMPDIR_WORK/gaps.tsv"

# === Daily trend ===
# Group outcomes by date, compute covered% and success%
# Paste date column from outcomes alongside joined results

paste <(awk -F'\t' '{split($1,a,"T"); print a[1]}' "$TMPDIR_WORK/outcomes.tsv") \
      "$TMPDIR_WORK/joined.tsv" > "$TMPDIR_WORK/trend_raw.tsv"

# Aggregate per-date stats, then sort externally (avoids gawk's asorti)
awk -F'\t' '{
    date = $1
    result = $2
    node = $3
    total[date]++
    if (result == "success") success[date]++
    if (node != "UNCOVERED") covered[date]++
}
END {
    for (d in total) {
        t = total[d]
        s = (d in success) ? success[d] : 0
        c = (d in covered) ? covered[d] : 0
        cpct = (t > 0) ? int(c * 100 / t) : 0
        spct = (t > 0) ? int(s * 100 / t) : 0
        printf "%s\t%d%%\t%d%%\n", d, cpct, spct
    }
}' "$TMPDIR_WORK/trend_raw.tsv" | sort -t$'\t' -k1 > "$TMPDIR_WORK/trend.tsv"

# === Output ===

echo "=== Intent Layer Telemetry ==="
echo ""
echo "Period: ${FIRST_DATE:-?} to ${LAST_DATE:-?}"
echo "Total edits: $TOTAL_EDITS"
echo "Covered edits: $COVERED_EDITS (${COVERED_PCT}%)"
echo "Uncovered edits: $UNCOVERED_EDITS (${UNCOVERED_PCT}%)"
echo "Success rate: ${SUCCESS_RATE}%"

# Per-node table
if [[ -s "$TMPDIR_WORK/per_node.tsv" ]]; then
    echo ""
    echo "## Per-Node Success Rates"
    echo ""
    printf "%-40s %-8s %-10s %s\n" "Node" "Edits" "Success" "Rate"
    while IFS=$'\t' read -r node edits success rate; do
        printf "%-40s %-8s %-10s %s%%\n" "$node" "$edits" "$success" "$rate"
    done < "$TMPDIR_WORK/per_node.tsv"
fi

# Coverage gaps
if [[ -s "$TMPDIR_WORK/gaps.tsv" ]]; then
    echo ""
    echo "## Coverage Gaps (files edited without AGENTS.md context)"
    echo ""
    printf "%-50s %s\n" "File" "Edits"
    while IFS=$'\t' read -r file count; do
        printf "%-50s %s\n" "$file" "$count"
    done < "$TMPDIR_WORK/gaps.tsv"
fi

# Trend
if [[ -s "$TMPDIR_WORK/trend.tsv" ]]; then
    echo ""
    echo "## Trend"
    echo ""
    printf "%-14s %-12s %s\n" "Date" "Covered%" "Success%"
    while IFS=$'\t' read -r date covered_pct success_pct; do
        printf "%-14s %-12s %s\n" "$date" "$covered_pct" "$success_pct"
    done < "$TMPDIR_WORK/trend.tsv"
fi

echo ""
