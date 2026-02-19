#!/usr/bin/env python3
"""Tail eval harness logs with per-source identification and color coding.

Watches the logs/ directory for active (growing) log files and streams
new lines tagged with a short identifier showing repo, task, condition,
and phase. Color-coded by condition for fast visual scanning.

Usage:
    # Tail all active logs
    ./scripts/tail-logs.py

    # Filter by condition
    ./scripts/tail-logs.py --condition intent_layer

    # Filter by phase (fix = Claude working, test = Docker tests, precheck = validation)
    ./scripts/tail-logs.py --phase fix

    # Filter by repo
    ./scripts/tail-logs.py --repo graphiti

    # Show all logs modified in last N seconds (default: 300)
    ./scripts/tail-logs.py --since 60

    # Follow only specific task substring
    ./scripts/tail-logs.py --task datetime

    # Show last N lines per file on attach (default: 5)
    ./scripts/tail-logs.py --tail 20

    # List active logs without tailing
    ./scripts/tail-logs.py --list
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# ANSI color codes
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Condition colors
    NONE = "\033[37m"        # white/gray
    FLAT_LLM = "\033[33m"    # yellow
    INTENT = "\033[32m"      # green

    # Phase colors (used for the phase tag)
    FIX = "\033[36m"         # cyan
    TEST = "\033[35m"        # magenta
    PRECHECK = "\033[34m"    # blue

    # Status highlights
    PASS = "\033[32;1m"      # bold green
    FAIL = "\033[31;1m"      # bold red
    WARN = "\033[33;1m"      # bold yellow

    @classmethod
    def for_condition(cls, cond: str) -> str:
        return {
            "none": cls.NONE,
            "flat_llm": cls.FLAT_LLM,
            "intent_layer": cls.INTENT,
        }.get(cond, cls.RESET)

    @classmethod
    def for_phase(cls, phase: str) -> str:
        return {
            "fix": cls.FIX,
            "test": cls.TEST,
            "precheck": cls.PRECHECK,
        }.get(phase, cls.DIM)


# Pattern: {repo}-{commit8}-{task_slug}-{hash8}-{condition}-r{rep}-{phase}.log
LOG_PATTERN = re.compile(
    r"^(?P<repo>[^-]+)"
    r"-(?P<commit>[0-9a-f]{8})"
    r"-(?P<task>.+?)"
    r"-(?P<hash>[0-9a-f]{8})"
    r"-(?P<condition>none|flat_llm|intent_layer)"
    r"-r(?P<rep>\d+)"
    r"-(?P<phase>\w+)"
    r"\.log$"
)


@dataclass
class LogFile:
    path: Path
    repo: str
    commit: str
    task: str
    task_hash: str
    condition: str
    rep: int
    phase: str
    offset: int = 0  # bytes read so far
    mtime: float = 0.0

    @property
    def tag(self) -> str:
        """Short identifier for display: task|cond|phase."""
        # Truncate task to keep tags readable
        short_task = self.task[:20]
        rep_str = f"r{self.rep}" if self.rep > 0 else ""
        parts = [short_task, self.condition, self.phase]
        if rep_str:
            parts.append(rep_str)
        return "|".join(parts)

    @property
    def colored_tag(self) -> str:
        cond_color = C.for_condition(self.condition)
        phase_color = C.for_phase(self.phase)
        short_task = self.task[:20]
        rep_str = f"|r{self.rep}" if self.rep > 0 else ""
        return (
            f"{C.DIM}{self.repo}{C.RESET}"
            f" {C.BOLD}{short_task}{C.RESET}"
            f" {cond_color}{self.condition}{C.RESET}"
            f" {phase_color}{self.phase}{C.RESET}"
            f"{rep_str}"
        )

    @classmethod
    def from_path(cls, path: Path) -> LogFile | None:
        m = LOG_PATTERN.match(path.name)
        if not m:
            return None
        return cls(
            path=path,
            repo=m.group("repo"),
            commit=m.group("commit"),
            task=m.group("task"),
            task_hash=m.group("hash"),
            condition=m.group("condition"),
            rep=int(m.group("rep")),
            phase=m.group("phase"),
        )


def highlight_line(line: str) -> str:
    """Add color highlights for notable patterns in log lines."""
    stripped = line.rstrip()
    if not stripped:
        return line

    # PASS/FAIL in test output
    if re.search(r"\bPASS(ED)?\b", stripped, re.IGNORECASE):
        return f"{C.PASS}{stripped}{C.RESET}"
    if re.search(r"\bFAIL(ED|URE)?\b", stripped, re.IGNORECASE):
        return f"{C.FAIL}{stripped}{C.RESET}"
    if re.search(r"\bERROR\b", stripped, re.IGNORECASE):
        return f"{C.FAIL}{stripped}{C.RESET}"
    if re.search(r"\bWARN(ING)?\b", stripped, re.IGNORECASE):
        return f"{C.WARN}{stripped}{C.RESET}"

    # Tool calls in fix logs
    if stripped.startswith("[tool]"):
        return f"{C.DIM}{stripped}{C.RESET}"

    return stripped


def discover_logs(log_dir: Path, since: float) -> list[LogFile]:
    """Find log files modified within the last `since` seconds."""
    cutoff = time.time() - since
    logs = []
    for p in log_dir.glob("*.log"):
        if p.stat().st_mtime < cutoff:
            continue
        lf = LogFile.from_path(p)
        if lf:
            lf.mtime = p.stat().st_mtime
            logs.append(lf)
    return sorted(logs, key=lambda l: l.mtime)


def matches_filters(lf: LogFile, args: argparse.Namespace) -> bool:
    if args.condition and lf.condition not in args.condition:
        return False
    if args.phase and lf.phase not in args.phase:
        return False
    if args.repo and not any(r.lower() in lf.repo.lower() for r in args.repo):
        return False
    if args.task and not any(t.lower() in lf.task.lower() for t in args.task):
        return False
    return True


def read_tail(lf: LogFile, n_lines: int) -> list[str]:
    """Read the last n_lines from a file and set offset to EOF."""
    try:
        content = lf.path.read_text()
    except OSError:
        return []
    lines = content.splitlines()
    lf.offset = len(content.encode())
    if n_lines <= 0:
        return []
    return lines[-n_lines:]


def read_new(lf: LogFile) -> list[str]:
    """Read new content since last offset."""
    try:
        size = lf.path.stat().st_size
    except OSError:
        return []
    if size <= lf.offset:
        return []
    try:
        with open(lf.path, "rb") as f:
            f.seek(lf.offset)
            new_bytes = f.read()
        lf.offset = size
        text = new_bytes.decode(errors="replace")
        # Split but keep partial last line? No — just split.
        lines = text.splitlines()
        return lines
    except OSError:
        return []


def print_tagged(lf: LogFile, lines: list[str], use_color: bool):
    """Print lines with tag prefix."""
    for line in lines:
        if use_color:
            tag = lf.colored_tag
            highlighted = highlight_line(line)
            print(f"{C.DIM}│{C.RESET} {tag} {C.DIM}│{C.RESET} {highlighted}")
        else:
            print(f"| {lf.tag} | {line.rstrip()}")


def list_logs(log_dir: Path, since: float, args: argparse.Namespace, use_color: bool):
    """List active logs matching filters."""
    logs = discover_logs(log_dir, since)
    logs = [lf for lf in logs if matches_filters(lf, args)]

    if not logs:
        print("No matching log files found.")
        return

    print(f"Found {len(logs)} log file(s) modified in last {since:.0f}s:\n")

    # Group by repo+task for readability
    by_group: dict[str, list[LogFile]] = {}
    for lf in logs:
        key = f"{lf.repo}/{lf.task}"
        by_group.setdefault(key, []).append(lf)

    for group_key, group_logs in sorted(by_group.items()):
        if use_color:
            print(f"  {C.BOLD}{group_key}{C.RESET}")
        else:
            print(f"  {group_key}")
        for lf in sorted(group_logs, key=lambda l: (l.condition, l.phase)):
            size = lf.path.stat().st_size
            age = time.time() - lf.mtime
            age_str = f"{age:.0f}s ago" if age < 120 else f"{age/60:.0f}m ago"
            if use_color:
                cond_color = C.for_condition(lf.condition)
                phase_color = C.for_phase(lf.phase)
                print(
                    f"    {cond_color}{lf.condition:14s}{C.RESET}"
                    f" {phase_color}{lf.phase:10s}{C.RESET}"
                    f" {C.DIM}{size:>8,}b  {age_str}{C.RESET}"
                )
            else:
                print(f"    {lf.condition:14s} {lf.phase:10s} {size:>8,}b  {age_str}")
    print()


def tail_loop(log_dir: Path, since: float, args: argparse.Namespace, use_color: bool):
    """Main tail loop: discover logs, print tail, then poll for new lines."""
    tracked: dict[str, LogFile] = {}
    poll_interval = 0.5  # seconds
    rediscover_interval = 5.0  # check for new files every N seconds
    last_discover = 0.0

    if use_color:
        header = f"{C.BOLD}Tailing logs in {log_dir}{C.RESET}"
        filters = []
        if args.condition:
            filters.append(f"condition={','.join(args.condition)}")
        if args.phase:
            filters.append(f"phase={','.join(args.phase)}")
        if args.repo:
            filters.append(f"repo={','.join(args.repo)}")
        if args.task:
            filters.append(f"task={','.join(args.task)}")
        if filters:
            header += f" {C.DIM}({', '.join(filters)}){C.RESET}"
        print(header)
        print(f"{C.DIM}Press Ctrl+C to stop{C.RESET}\n")
    else:
        print(f"Tailing logs in {log_dir}")
        print("Press Ctrl+C to stop\n")

    try:
        while True:
            now = time.time()

            # Periodically discover new log files
            if now - last_discover >= rediscover_interval:
                logs = discover_logs(log_dir, since)
                for lf in logs:
                    key = str(lf.path)
                    if key not in tracked and matches_filters(lf, args):
                        # New file — show tail
                        tail_lines = read_tail(lf, args.tail)
                        if tail_lines:
                            if use_color:
                                print(f"\n{C.DIM}── attached to {C.RESET}{lf.colored_tag} {C.DIM}──{C.RESET}")
                            else:
                                print(f"\n-- attached to {lf.tag} --")
                            print_tagged(lf, tail_lines, use_color)
                        tracked[key] = lf
                last_discover = now

            # Check tracked files for new content
            any_output = False
            for lf in tracked.values():
                new_lines = read_new(lf)
                if new_lines:
                    print_tagged(lf, new_lines, use_color)
                    any_output = True

            if not any_output:
                time.sleep(poll_interval)

    except KeyboardInterrupt:
        if use_color:
            print(f"\n{C.DIM}Stopped.{C.RESET}")
        else:
            print("\nStopped.")


def main():
    # Line-buffer stdout so piped output appears immediately
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(
        description="Tail eval harness logs with per-source identification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # tail all active logs
  %(prog)s --condition intent_layer     # only intent_layer runs
  %(prog)s --phase fix                  # only Claude fix phases
  %(prog)s --phase fix --phase test     # fix and test phases
  %(prog)s --repo graphiti --task datetime  # specific repo+task
  %(prog)s --list                       # show active logs, don't tail
  %(prog)s --since 60                   # only logs from last 60s
  %(prog)s --tail 0                     # no backlog, new lines only
  %(prog)s --no-color                   # pipe-friendly plain output
""",
    )
    parser.add_argument(
        "--condition", "-c",
        action="append",
        choices=["none", "flat_llm", "intent_layer"],
        help="Filter by condition (repeatable)",
    )
    parser.add_argument(
        "--phase", "-p",
        action="append",
        choices=["fix", "test", "precheck"],
        help="Filter by phase (repeatable)",
    )
    parser.add_argument(
        "--repo", "-r",
        action="append",
        help="Filter by repo name substring (repeatable)",
    )
    parser.add_argument(
        "--task", "-k",
        action="append",
        help="Filter by task name substring (repeatable)",
    )
    parser.add_argument(
        "--since", "-s",
        type=float,
        default=300,
        help="Only logs modified within last N seconds (default: 300)",
    )
    parser.add_argument(
        "--tail", "-n",
        type=int,
        default=5,
        help="Show last N lines per file on attach (default: 5)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List active log files and exit (don't tail)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable color output (for piping)",
    )
    parser.add_argument(
        "--dir", "-d",
        type=Path,
        default=None,
        help="Log directory (default: logs/ relative to script)",
    )

    args = parser.parse_args()

    # Resolve log directory
    if args.dir:
        log_dir = args.dir
    else:
        # Default: logs/ relative to the eval-harness root
        script_dir = Path(__file__).resolve().parent
        log_dir = script_dir.parent / "logs"

    if not log_dir.is_dir():
        print(f"Log directory not found: {log_dir}", file=sys.stderr)
        sys.exit(1)

    use_color = not args.no_color and sys.stdout.isatty()

    if args.list:
        list_logs(log_dir, args.since, args, use_color)
    else:
        tail_loop(log_dir, args.since, args, use_color)


if __name__ == "__main__":
    main()
