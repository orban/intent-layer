# lib/budget.py
"""Thin wrapper around nightshift CLI for budget awareness.

All functions are advisory — they return None on any failure (nightshift not
installed, timeout, parse error). The budget system never blocks eval runs.
"""
from __future__ import annotations

import json
import subprocess


def fmt_tokens(n: int | float) -> str:
    """Format a token count for human display: '1.2M' or '384k'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{n / 1_000:.0f}k"


def get_budget_status() -> dict | None:
    """Shell out to `nightshift stats --json` and return the Claude budget projection.

    Returns dict with keys like remaining_tokens, will_exhaust_before_reset,
    est_hours_remaining, reset_at, current_used_pct, weekly_budget.
    Returns None if nightshift isn't installed or the command fails.
    """
    try:
        result = subprocess.run(
            ["nightshift", "stats", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None

    projection = data.get("budget_projection")
    if projection is None:
        return None

    return projection


def check_budget(work_queue_size: int, avg_tokens_per_task: int = 50_000, status: dict | None = None) -> str | None:
    """Pre-flight budget check. Returns warning string if budget looks tight, None if OK.

    Compares estimated run cost against remaining_tokens from nightshift.
    Pass a pre-fetched status dict to avoid a redundant subprocess call.
    Returns None if nightshift is unavailable or budget looks sufficient.
    """
    if status is None:
        status = get_budget_status()
    if status is None:
        return None

    remaining = status.get("remaining_tokens")
    if not isinstance(remaining, (int, float)):
        return None

    estimated = work_queue_size * avg_tokens_per_task
    used_pct = status.get("current_used_pct", 0)
    reset_at = status.get("reset_at", "unknown")
    est_hours = status.get("est_hours_remaining")
    will_exhaust = status.get("will_exhaust_before_reset", False)

    parts = [
        f"Budget warning: estimated {work_queue_size} tasks x {avg_tokens_per_task // 1000}k tokens = {fmt_tokens(estimated)} tokens",
        f"  Nightshift reports {fmt_tokens(remaining)} remaining ({used_pct:.0f}% used), resets {reset_at}",
    ]

    if est_hours is not None:
        parts.append(f"  Projected to exhaust in ~{est_hours:.1f} hours")

    if estimated > remaining:
        parts.append("  Run will likely exceed remaining budget")
    elif will_exhaust:
        parts.append("  Budget projected to exhaust before reset (even without this run)")

    # Only warn if there's something to warn about
    if estimated > remaining or will_exhaust:
        return "\n".join(parts)

    return None


def refresh_budget_snapshot() -> None:
    """Fire-and-forget: ask nightshift to refresh its local budget snapshot.

    Runs `nightshift budget snapshot --local-only` which reads local stats
    files without tmux scraping. Non-blocking — failures are silently ignored.
    """
    try:
        subprocess.Popen(
            ["nightshift", "budget", "snapshot", "--local-only"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        pass
