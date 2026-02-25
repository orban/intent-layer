# lib/monitor.py
"""Eval monitor: automated eval supervisor.

Polls .eval-status.json and issues commands via .eval-control/ to manage
a running eval. All decisions are rule-based — no LLM reasoning needed.

Usage:
    python lib/monitor.py --results-dir results/
    python lib/monitor.py --results-dir results/ --poll-interval 30
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from lib.reporter import Reporter

log = logging.getLogger("monitor")


@dataclass
class MonitorConfig:
    results_dir: Path
    poll_interval: int = 15  # seconds between status checks
    stall_timeout: int = 300  # 5 min without progress → stalled
    infra_skip_threshold: int = 3  # skip task after N infra-only failures
    budget_pause_pct: float = 0.10  # pause when < 10% budget remaining
    max_workers_recovery: int = 4  # default workers after Docker recovery


@dataclass
class MonitorState:
    """Tracks the monitor's view of the eval run across poll cycles."""
    last_completed: int = 0
    last_progress_time: float = field(default_factory=time.time)
    task_infra_counts: dict[str, int] = field(default_factory=dict)
    skipped_tasks: set[str] = field(default_factory=set)
    actions_taken: list[dict] = field(default_factory=list)
    docker_restarts: int = 0
    paused_by_monitor: bool = False


def read_status(results_dir: Path) -> dict | None:
    """Read .eval-status.json, return None if missing or corrupt."""
    status_path = results_dir / ".eval-status.json"
    if not status_path.exists():
        return None
    try:
        with open(status_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def send_command(results_dir: Path, command: str, value: str = "") -> bool:
    """Write a command file to .eval-control/ for the eval to consume."""
    control_dir = results_dir / ".eval-control"
    control_dir.mkdir(parents=True, exist_ok=True)
    cmd_path = control_dir / command
    try:
        cmd_path.write_text(value)
        return True
    except IOError as e:
        log.error("Failed to write command %s: %s", command, e)
        return False


def read_checkpoint(results_dir: Path) -> dict | None:
    """Read the latest in-progress checkpoint for per-task analysis."""
    checkpoints = sorted(results_dir.glob("in-progress-*.json"), reverse=True)
    if not checkpoints:
        return None
    try:
        with open(checkpoints[0]) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def count_task_infra_failures(checkpoint: dict) -> dict[str, int]:
    """Count infra-only failures per task from checkpoint results."""
    counts: dict[str, int] = {}
    for task_result in checkpoint.get("results", []):
        task_id = task_result["task_id"]
        total_infra = 0
        total_runs = 0
        skip_keys = {"task_id", "deltas"}
        cond_keys = [k for k in task_result if k not in skip_keys]
        for cond in cond_keys:
            cond_data = task_result.get(cond)
            if not cond_data:
                continue
            runs = cond_data.get("runs", [])
            if not runs:
                # Single run format
                if cond_data.get("error", "").startswith(
                    Reporter.INFRA_ERROR_PREFIXES
                ):
                    total_infra += 1
                total_runs += 1
            else:
                for run in runs:
                    total_runs += 1
                    if run.get("error", "").startswith(
                        Reporter.INFRA_ERROR_PREFIXES
                    ):
                        total_infra += 1
        # Only count if ALL runs are infra failures
        if total_runs > 0 and total_infra == total_runs:
            counts[task_id] = total_infra
    return counts


def check_docker() -> bool:
    """Check if Docker daemon is responsive."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def restart_docker() -> bool:
    """Attempt to restart Docker via OrbStack (macOS)."""
    import subprocess
    try:
        subprocess.run(["open", "-a", "OrbStack"], timeout=10)
        # Wait for Docker to come back
        for _ in range(12):  # 60 seconds max
            time.sleep(5)
            if check_docker():
                return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def evaluate_policies(
    status: dict,
    state: MonitorState,
    config: MonitorConfig,
) -> list[dict]:
    """Apply policy rules and return list of actions to take.

    Each action is {"type": str, "command": str, "value": str, "reason": str}.
    """
    actions: list[dict] = []
    now = time.time()

    completed = status.get("completed", 0)
    remaining = status.get("remaining", 0)
    infra_rate = status.get("infra_rate", 0)
    paused = status.get("paused", False)

    # ── Stall detection ──────────────────────────────────────────
    if completed > state.last_completed:
        state.last_completed = completed
        state.last_progress_time = now
    elif remaining > 0 and not paused:
        stall_seconds = now - state.last_progress_time
        if stall_seconds > config.stall_timeout:
            # Check if Docker is the problem
            if not check_docker():
                actions.append({
                    "type": "docker_restart",
                    "reason": f"No progress for {stall_seconds:.0f}s, Docker unresponsive",
                })
            else:
                actions.append({
                    "type": "log_warning",
                    "reason": f"No progress for {stall_seconds:.0f}s but Docker is healthy. Eval may be stuck.",
                })

    # ── Infra-heavy task skipping ────────────────────────────────
    checkpoint = read_checkpoint(config.results_dir)
    if checkpoint:
        task_infra = count_task_infra_failures(checkpoint)
        for task_id, count in task_infra.items():
            if (count >= config.infra_skip_threshold
                    and task_id not in state.skipped_tasks):
                actions.append({
                    "type": "skip_task",
                    "command": "skip-task",
                    "value": task_id,
                    "reason": f"Task {task_id}: {count} consecutive infra failures",
                })

    # ── Worker recovery ──────────────────────────────────────────
    workers = status.get("workers", 0)
    if workers < config.max_workers_recovery and infra_rate < 0.1 and remaining > 5:
        actions.append({
            "type": "set_workers",
            "command": "set-workers",
            "value": str(config.max_workers_recovery),
            "reason": f"Infra rate low ({infra_rate:.0%}), recovering workers {workers} → {config.max_workers_recovery}",
        })

    # ── Eval complete ────────────────────────────────────────────
    if remaining == 0 and completed > 0:
        actions.append({
            "type": "eval_complete",
            "reason": f"Eval finished: {completed} runs, pass rate {status.get('pass_rate', 0):.0%}",
        })

    return actions


def execute_actions(
    actions: list[dict],
    state: MonitorState,
    config: MonitorConfig,
) -> None:
    """Execute the actions returned by evaluate_policies."""
    for action in actions:
        action_type = action["type"]
        reason = action["reason"]
        timestamp = time.strftime("%H:%M:%S")

        if action_type == "docker_restart":
            log.warning("[%s] %s — attempting Docker restart", timestamp, reason)
            if restart_docker():
                state.docker_restarts += 1
                log.info("[%s] Docker restarted successfully (#%d)", timestamp, state.docker_restarts)
                # Resume if we paused
                if state.paused_by_monitor:
                    send_command(config.results_dir, "resume")
                    state.paused_by_monitor = False
                state.last_progress_time = time.time()
            else:
                log.error("[%s] Docker restart failed", timestamp)
                # Pause the eval to prevent wasting budget
                send_command(config.results_dir, "pause")
                state.paused_by_monitor = True

        elif action_type == "skip_task":
            task_id = action["value"]
            log.warning("[%s] SKIP %s — %s", timestamp, task_id, reason)
            send_command(config.results_dir, "skip-task", task_id)
            state.skipped_tasks.add(task_id)

        elif action_type == "set_workers":
            new_workers = action["value"]
            log.info("[%s] SET-WORKERS %s — %s", timestamp, new_workers, reason)
            send_command(config.results_dir, "set-workers", new_workers)

        elif action_type == "budget_pause":
            log.warning("[%s] PAUSE — %s", timestamp, reason)
            send_command(config.results_dir, "pause")
            state.paused_by_monitor = True

        elif action_type == "eval_complete":
            log.info("[%s] COMPLETE — %s", timestamp, reason)

        elif action_type == "log_warning":
            log.warning("[%s] %s", timestamp, reason)

        state.actions_taken.append({
            "time": timestamp,
            **action,
        })


def run_loop(config: MonitorConfig) -> MonitorState:
    """Main polling loop. Runs until eval completes or is interrupted."""
    state = MonitorState()
    log.info(
        "Eval monitor started — watching %s (poll every %ds)",
        config.results_dir, config.poll_interval,
    )

    try:
        while True:
            status = read_status(config.results_dir)
            if status is None:
                log.debug("No status file yet, waiting...")
                time.sleep(config.poll_interval)
                continue

            remaining = status.get("remaining", 0)
            completed = status.get("completed", 0)
            log.info(
                "Status: %d/%d completed, %d remaining, workers=%d, infra_rate=%.0f%%",
                completed, completed + remaining, remaining,
                status.get("workers", 0),
                status.get("infra_rate", 0) * 100,
            )

            actions = evaluate_policies(status, state, config)
            if actions:
                execute_actions(actions, state, config)

            # Stop if eval is done
            if remaining == 0 and completed > 0:
                log.info("Eval complete. Monitor shutting down.")
                break

            time.sleep(config.poll_interval)

    except KeyboardInterrupt:
        log.info("Monitor interrupted by user.")

    # Write action log
    log_path = config.results_dir / ".monitor-log.json"
    with open(log_path, "w") as f:
        json.dump(state.actions_taken, f, indent=2)
    log.info("Action log written to %s (%d actions)", log_path, len(state.actions_taken))

    return state


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Eval monitor: automated eval supervisor",
    )
    parser.add_argument(
        "--results-dir", required=True, type=Path,
        help="Path to eval results directory (contains .eval-status.json)",
    )
    parser.add_argument(
        "--poll-interval", type=int, default=15,
        help="Seconds between status checks (default: 15)",
    )
    parser.add_argument(
        "--stall-timeout", type=int, default=300,
        help="Seconds without progress before stall alert (default: 300)",
    )
    parser.add_argument(
        "--infra-skip-threshold", type=int, default=3,
        help="Skip task after N infra-only failures (default: 3)",
    )
    parser.add_argument(
        "--max-workers", type=int, default=4,
        help="Worker count to recover to after infra stabilizes (default: 4)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [monitor] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    config = MonitorConfig(
        results_dir=args.results_dir,
        poll_interval=args.poll_interval,
        stall_timeout=args.stall_timeout,
        infra_skip_threshold=args.infra_skip_threshold,
        max_workers_recovery=args.max_workers,
    )
    run_loop(config)


if __name__ == "__main__":
    main()
