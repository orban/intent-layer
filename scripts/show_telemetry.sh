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

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "${BASH_SOURCE[0]}")")}"
source "$PLUGIN_ROOT/lib/common.sh"

display_field() {
    telemetry_unescape_field "$1" | tr '\n\r' '  '
}

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
    - Per-node success/failure rates from normalized outcome rows
    - Coverage gaps (files edited without AGENTS.md coverage)
    - Completeness / malformed-row metrics and daily trend

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

awk -F'\t' '
BEGIN { malformed=0 }
NF >= 7 {
    coverage = $5
    node = $6
    if (coverage == "" || coverage == "unknown") {
        coverage = (node != "" && node != "None") ? "covered" : "uncovered"
    }
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", $1, $2, $3, $4, coverage, node, $7
    next
}
NF == 4 {
    printf "%s\t%s\t%s\t%s\tunknown\tNone\tlegacy-format\n", $1, $2, $3, $4
    next
}
{ malformed++ }
END {
    printf "%d\n", malformed > "'"$TMPDIR_WORK"'/outcomes_malformed.count"
}
' "$OUTCOMES_LOG" > "$TMPDIR_WORK/outcomes.tsv"

if [[ -f "$INJECTIONS_LOG" && -s "$INJECTIONS_LOG" ]]; then
    awk -F'\t' '
    BEGIN { malformed=0 }
    NF >= 6 {
        printf "%s\t%s\t%s\t%s\t%s\t%s\n", $1, $2, $3, $4, $5, $6
        next
    }
    NF == 4 {
        printf "%s\tunknown\t%s\tcovered\t%s\t%s\n", $1, $2, $3, $4
        next
    }
    { malformed++ }
    END {
        printf "%d\n", malformed > "'"$TMPDIR_WORK"'/injections_malformed.count"
    }
    ' "$INJECTIONS_LOG" > "$TMPDIR_WORK/injections.tsv"
else
    touch "$TMPDIR_WORK/injections.tsv"
    printf '0\n' > "$TMPDIR_WORK/injections_malformed.count"
fi

OUTCOME_MALFORMED=$(cat "$TMPDIR_WORK/outcomes_malformed.count")
INJECTION_MALFORMED=$(cat "$TMPDIR_WORK/injections_malformed.count")

# === Summary stats ===

TOTAL_EDITS=$(wc -l < "$TMPDIR_WORK/outcomes.tsv" | tr -d ' ')
SUCCESS_EDITS=$(awk -F'\t' '$3 == "success"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')
FAILURE_EDITS=$(awk -F'\t' '$3 == "failure"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')

# === Compute metrics ===

COVERED_EDITS=$(awk -F'\t' '$5 == "covered"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')
UNCOVERED_EDITS=$(awk -F'\t' '$5 == "uncovered"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')
UNKNOWN_COVERAGE_EDITS=$(awk -F'\t' '$5 == "unknown"' "$TMPDIR_WORK/outcomes.tsv" | wc -l | tr -d ' ')
TOTAL_INJECTIONS=$(wc -l < "$TMPDIR_WORK/injections.tsv" | tr -d ' ')

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
awk -F'\t' '$5 == "covered" && $6 != "" && $6 != "None" {
    node = $6
    total[node]++
    if ($3 == "success") success[node]++
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
}' "$TMPDIR_WORK/outcomes.tsv" | sort -t$'\t' -k2 -rn > "$TMPDIR_WORK/per_node.tsv"

# === Coverage gaps ===
# Files edited without AGENTS.md context, grouped by file

awk -F'\t' '$5 == "uncovered" {
    files[$4]++
}
END {
    for (f in files) {
        printf "%s\t%d\n", f, files[f]
    }
}' "$TMPDIR_WORK/outcomes.tsv" | sort -t$'\t' -k2 -rn > "$TMPDIR_WORK/gaps.tsv"

# === Daily trend ===
# Group outcomes by date, compute covered% and success%
# Paste date column from outcomes alongside joined results

paste <(awk -F'\t' '{split($1,a,"T"); print a[1]}' "$TMPDIR_WORK/outcomes.tsv") \
      "$TMPDIR_WORK/outcomes.tsv" > "$TMPDIR_WORK/trend_raw.tsv"

# Aggregate per-date stats, then sort externally (avoids gawk's asorti)
awk -F'\t' '{
    date = $1
    result = $4
    coverage = $6
    total[date]++
    if (result == "success") success[date]++
    if (coverage == "covered") covered[date]++
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
echo "Total injections: $TOTAL_INJECTIONS"
echo "Covered edits: $COVERED_EDITS (${COVERED_PCT}%)"
echo "Uncovered edits: $UNCOVERED_EDITS (${UNCOVERED_PCT}%)"
echo "Unknown coverage rows: $UNKNOWN_COVERAGE_EDITS"
echo "Success rate: ${SUCCESS_RATE}%"
echo "Malformed rows skipped: outcomes=$OUTCOME_MALFORMED, injections=$INJECTION_MALFORMED"

# Per-node table
if [[ -s "$TMPDIR_WORK/per_node.tsv" ]]; then
    echo ""
    echo "## Per-Node Success Rates"
    echo ""
    printf "%-40s %-8s %-10s %s\n" "Node" "Edits" "Success" "Rate"
    while IFS=$'\t' read -r node edits success rate; do
        printf "%-40s %-8s %-10s %s%%\n" "$(display_field "$node")" "$edits" "$success" "$rate"
    done < "$TMPDIR_WORK/per_node.tsv"
fi

# Coverage gaps
if [[ -s "$TMPDIR_WORK/gaps.tsv" ]]; then
    echo ""
    echo "## Coverage Gaps (files edited without AGENTS.md context)"
    echo ""
    printf "%-50s %s\n" "File" "Edits"
    while IFS=$'\t' read -r file count; do
        printf "%-50s %s\n" "$(display_field "$file")" "$count"
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
