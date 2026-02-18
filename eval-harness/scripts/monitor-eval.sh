#!/usr/bin/env bash
set -euo pipefail

# Monitor an eval run, logging progress and detecting problems.
# Usage: ./scripts/monitor-eval.sh <PID> <LOG_FILE>

PID="${1:?Usage: monitor-eval.sh <PID> <LOG_FILE>}"
LOG_FILE="${2:?Usage: monitor-eval.sh <PID> <LOG_FILE>}"
MONITOR_LOG="logs/monitor-$(date +%Y%m%d-%H%M%S).log"
CHECK_INTERVAL=60  # seconds between checks
STALL_THRESHOLD=300  # seconds without log change = stalled
CHILD_STALL_THRESHOLD=900  # 15 min for a single Claude subprocess

log() {
    local ts
    ts="$(date '+%H:%M:%S')"
    echo "[$ts] $*" | tee -a "$MONITOR_LOG"
}

log "Monitor started for PID=$PID, log=$LOG_FILE"
log "Writing monitor log to $MONITOR_LOG"
log "Check interval: ${CHECK_INTERVAL}s, stall threshold: ${STALL_THRESHOLD}s"

last_log_size=0
last_log_change=$(date +%s)
last_line_count=0
pass_count=0
fail_count=0
infra_count=0
completed_count=0

while true; do
    # --- Check if main process is alive ---
    if ! ps -p "$PID" > /dev/null 2>&1; then
        log "DONE: Main process $PID has exited"
        # Show final results
        if [[ -f "$LOG_FILE" ]]; then
            log "=== Final log tail ==="
            tail -20 "$LOG_FILE" | while IFS= read -r line; do log "  $line"; done
        fi
        # Find the latest results file
        latest_json=$(ls -t results/*.json 2>/dev/null | head -1)
        if [[ -n "$latest_json" ]]; then
            log "Latest results: $latest_json"
            latest_md="${latest_json%.json}.md"
            if [[ -f "$latest_md" ]]; then
                log "=== Results summary ==="
                head -20 "$latest_md" | while IFS= read -r line; do log "  $line"; done
            fi
        fi
        log "Monitor exiting"
        exit 0
    fi

    # --- Check log file growth ---
    if [[ -f "$LOG_FILE" ]]; then
        current_size=$(wc -c < "$LOG_FILE" | tr -d ' ')
        current_lines=$(wc -l < "$LOG_FILE" | tr -d ' ')
        now=$(date +%s)

        if [[ "$current_size" -ne "$last_log_size" ]]; then
            last_log_change=$now
            new_lines=$((current_lines - last_line_count))

            if [[ "$new_lines" -gt 0 ]]; then
                # Parse new lines for events
                tail -"$new_lines" "$LOG_FILE" | while IFS= read -r line; do
                    case "$line" in
                        *": PASS"*)
                            log "PASS: $line"
                            ;;
                        *": FAIL"*)
                            log "FAIL: $line"
                            ;;
                        *"TIMEOUT"*)
                            log "TIMEOUT: $line"
                            ;;
                        *"Infrastructure error"*)
                            log "INFRA ERROR: $line"
                            ;;
                        *"Results written"*)
                            log "RESULTS: $line"
                            ;;
                        *"warmup"*|*"Pre-warming"*)
                            log "WARMUP: $line"
                            ;;
                        *"Cleaned up"*)
                            log "CLEANUP: $line"
                            ;;
                    esac
                done
            fi

            last_log_size=$current_size
            last_line_count=$current_lines
        else
            stall_duration=$((now - last_log_change))
            if [[ "$stall_duration" -ge "$STALL_THRESHOLD" ]]; then
                log "WARNING: Log unchanged for ${stall_duration}s (threshold: ${STALL_THRESHOLD}s)"

                # Check what child processes are doing
                child_pids=$(pgrep -P "$PID" 2>/dev/null || true)
                if [[ -n "$child_pids" ]]; then
                    for cpid in $child_pids; do
                        child_info=$(ps -o pid,etime,cputime,%cpu,state -p "$cpid" 2>/dev/null | tail -1)
                        log "  Child process: $child_info"

                        # Check for deeply stuck Claude subprocesses
                        elapsed_raw=$(ps -o etime= -p "$cpid" 2>/dev/null | tr -d ' ')
                        # Parse elapsed time (MM:SS or HH:MM:SS)
                        if [[ "$elapsed_raw" =~ ^([0-9]+):([0-9]+):([0-9]+)$ ]]; then
                            elapsed_secs=$(( ${BASH_REMATCH[1]} * 3600 + ${BASH_REMATCH[2]} * 60 + ${BASH_REMATCH[3]} ))
                        elif [[ "$elapsed_raw" =~ ^([0-9]+):([0-9]+)$ ]]; then
                            elapsed_secs=$(( ${BASH_REMATCH[1]} * 60 + ${BASH_REMATCH[2]} ))
                        else
                            elapsed_secs=0
                        fi

                        if [[ "$elapsed_secs" -ge "$CHILD_STALL_THRESHOLD" ]]; then
                            log "  WARNING: Child $cpid running for ${elapsed_secs}s (>${CHILD_STALL_THRESHOLD}s)"
                            # Check CPU — if 0%, it's truly stuck
                            cpu=$(ps -o %cpu= -p "$cpid" 2>/dev/null | tr -d ' ')
                            if [[ "${cpu%.*}" == "0" ]]; then
                                log "  CRITICAL: Child $cpid at 0% CPU for ${elapsed_secs}s — likely hung"
                                log "  Killing hung child $cpid"
                                kill "$cpid" 2>/dev/null || true
                                log "  Sent SIGTERM to $cpid"
                            fi
                        fi
                    done
                else
                    log "  No child processes found — main process may be stuck"
                fi
            fi
        fi
    else
        log "WARNING: Log file $LOG_FILE does not exist yet"
    fi

    # --- Periodic summary ---
    if [[ -f "$LOG_FILE" ]]; then
        total_pass=$(grep -c ": PASS" "$LOG_FILE" 2>/dev/null || echo 0)
        total_fail=$(grep -c ": FAIL" "$LOG_FILE" 2>/dev/null || echo 0)
        total_infra=$(grep -c "Infrastructure error" "$LOG_FILE" 2>/dev/null || echo 0)
        total_done=$((total_pass + total_fail))

        # Only log summary when counts change
        summary_key="${total_pass}-${total_fail}-${total_infra}"
        if [[ "${summary_key}" != "${last_summary_key:-}" ]]; then
            log "PROGRESS: ${total_done}/243 done (${total_pass} pass, ${total_fail} fail, ${total_infra} infra errors)"
            last_summary_key="$summary_key"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
