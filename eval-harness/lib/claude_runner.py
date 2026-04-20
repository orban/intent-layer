# lib/claude_runner.py
from __future__ import annotations
import subprocess
import threading
import time
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClaudeResult:
    exit_code: int
    wall_clock_seconds: float
    input_tokens: int
    output_tokens: int
    tool_calls: int
    stdout: str
    stderr: str
    timed_out: bool = False
    cost_usd: float = 0.0
    num_turns: int = 0
    # Per-event arrival records from the stream-json path; one dict per
    # NDJSON line we read. Empty when the fast (non-streaming) path runs.
    # See _extract_stream_event for the dict shape.
    stream_events: list[dict] = field(default_factory=list)


def parse_claude_output(stdout: str) -> dict:
    """Parse Claude's JSON output for metrics.

    Claude CLI can output either:
    - A dict with "usage" and "tool_calls" keys (newer format)
    - A list of messages (older/streaming format)
    """
    try:
        data = json.loads(stdout)

        # Handle list output (array of messages)
        if isinstance(data, list):
            # Count tool_use blocks in messages and sum up usage from assistant messages
            tool_calls = 0
            input_tokens = 0
            output_tokens = 0
            for msg in data:
                if isinstance(msg, dict):
                    # Check for usage in message
                    usage = msg.get("usage", {})
                    if isinstance(usage, dict):
                        input_tokens += usage.get("input_tokens", 0)
                        output_tokens += usage.get("output_tokens", 0)
                    # Count tool_use blocks in content
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                tool_calls += 1
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls
            }

        # Handle dict output (--print --output-format json)
        # Keys: type, usage, num_turns, result, total_cost_usd, etc.
        if isinstance(data, dict):
            usage = data.get("usage", {})
            if not isinstance(usage, dict):
                usage = {}
            # Sum all input token types — Claude caches prompts aggressively,
            # so input_tokens alone undercounts (most served from cache)
            input_tokens = (
                usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
            num_turns = data.get("num_turns", 0)
            tools = data.get("tool_calls")
            tool_count = len(tools) if tools else (num_turns if num_turns else 0)
            return {
                "input_tokens": input_tokens,
                "output_tokens": usage.get("output_tokens", 0),
                "tool_calls": tool_count,
                "cost_usd": data.get("total_cost_usd", 0),
                "num_turns": num_turns,
            }

        return {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0}


def _extract_stream_event(line: str, t: float) -> tuple[dict | None, str | None]:
    """Parse a stream-json NDJSON line into (record, summary).

    `record`  — minimal structured dict suitable for per-trial timing analysis,
                with keys:
                  t            relative seconds since claude_runner start
                  type         "assistant" | "user" | "result" | "system" | ...
                  tools        list[str] of tool names (assistant events only)
                  out          output_tokens delta (when usage block present)
                  cache_read   cache_read_input_tokens delta
                  cache_create cache_creation_input_tokens delta
                  inp          raw input_tokens delta (rare; usually all cached)
                  num_turns    final turn count (result events only)
                  cost_usd     cumulative cost (result events only)

    `summary` — human-readable line for the live progress log, matching the
                pre-existing format. None when the event isn't worth logging.

    Returns (None, None) on parse failure or non-dict payloads. The caller
    should still record an arrival timestamp for unparseable lines if it
    wants idle-gap visibility, but most care only about structured events.
    """
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None, None
    if not isinstance(event, dict):
        return None, None

    etype = event.get("type", "")
    record: dict = {"t": round(t, 3), "type": etype}

    if etype == "assistant":
        msg = event.get("message", {})
        content = msg.get("content", []) if isinstance(msg, dict) else []
        usage = msg.get("usage", {}) if isinstance(msg, dict) else {}
        if isinstance(usage, dict):
            for short, long in (
                ("inp", "input_tokens"),
                ("out", "output_tokens"),
                ("cache_read", "cache_read_input_tokens"),
                ("cache_create", "cache_creation_input_tokens"),
            ):
                v = usage.get(long, 0)
                if v:
                    record[short] = v
        tools: list[str] = []
        parts: list[str] = []
        for block in (content if isinstance(content, list) else []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = block.get("name", "?")
                tools.append(name)
                inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
                if name in ("Read", "Edit", "Write"):
                    parts.append(f"{name} {inp.get('file_path', '?')}")
                elif name == "Bash":
                    parts.append(f"Bash: {inp.get('command', '?')[:80]}")
                elif name == "Grep":
                    parts.append(f"Grep: {inp.get('pattern', '?')}")
                elif name == "Glob":
                    parts.append(f"Glob: {inp.get('pattern', '?')}")
                else:
                    parts.append(name)
        if tools:
            record["tools"] = tools
        summary = "  ".join(f"[tool] {p}" for p in parts) if parts else None
        return record, summary

    if etype == "result":
        cost = event.get("total_cost_usd", 0)
        turns = event.get("num_turns", "?")
        if isinstance(cost, (int, float)):
            record["cost_usd"] = cost
        if isinstance(turns, int):
            record["num_turns"] = turns
        return record, f"[result] {turns} turns, ${cost:.4f}"

    return record, None


def _summarize_stream_event(line: str) -> str | None:
    """Back-compat wrapper. Prefer _extract_stream_event for new callers."""
    _, summary = _extract_stream_event(line, 0.0)
    return summary


def parse_stream_json_output(lines: list[str]) -> dict:
    """Parse stream-json NDJSON output for metrics.

    Finds the final ``{"type": "result", ...}`` event for aggregated
    metrics.  Falls back to counting tool_use blocks across assistant
    events.
    """
    result_event: dict | None = None
    counted_tool_calls = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue

        etype = event.get("type", "")

        # Count tool_use blocks in assistant messages
        if etype == "assistant":
            msg = event.get("message", {})
            content = msg.get("content", []) if isinstance(msg, dict) else []
            for block in (content if isinstance(content, list) else []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    counted_tool_calls += 1

        # Track result event (last one wins)
        if etype == "result":
            result_event = event

    # Use result event if found (same shape as --output-format json)
    if result_event:
        return parse_claude_output(json.dumps(result_event))

    # Fallback: return counted tool calls, zero tokens (no summary available)
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_calls": counted_tool_calls,
    }


def _wait_for_proc(
    proc: subprocess.Popen,
    start: float,
    timeout: float,
    idle_timeout: float | None,
    stream_events: list[dict],
    poll_interval: float = 2.0,
) -> str | None:
    """Poll proc until it exits, is hard-killed at `timeout`, or is killed for
    going `idle_timeout` seconds without a new stream event.

    Returns None when the process finished on its own, `"timeout"` when we
    killed it for the hard wall-clock ceiling, or `"idle"` when we killed it
    because no new stream-json events arrived for `idle_timeout` seconds.

    `stream_events` is read concurrently — it is appended from the stdout
    reader thread. We only read the tail timestamp, which is safe because
    list append and index access are atomic in CPython and the list is
    monotonic (events are never removed).
    """
    deadline = start + timeout
    while True:
        if proc.poll() is not None:
            return None
        now = time.time()
        if now >= deadline:
            proc.kill()
            proc.wait()
            return "timeout"
        if idle_timeout and idle_timeout > 0:
            last_event_wall = (
                start + stream_events[-1]["t"] if stream_events else start
            )
            if now - last_event_wall >= idle_timeout:
                proc.kill()
                proc.wait()
                return "idle"
        time.sleep(poll_interval)


def run_claude(
    workspace: str,
    prompt: str,
    timeout: int = 300,
    max_turns: int = 50,
    model: str | None = None,
    extra_env: dict[str, str] | None = None,
    stderr_log: str | Path | None = None,
    idle_timeout: float | None = None,
) -> ClaudeResult:
    """Run Claude Code CLI and capture metrics.

    Args:
        stderr_log: Path to write live progress in real-time.  When set,
            uses ``--output-format stream-json`` and writes human-readable
            event summaries (tool calls, results) to this file so callers
            can ``tail -f`` it for live monitoring.
        idle_timeout: When set and > 0, kills the Claude subprocess if no new
            stream-json events arrive for this many seconds. Only active on
            the streaming path (stderr_log set). The diagnostic finding that
            prompted this: failed trials sit silently on an API stall for
            minutes before the hard timeout fires; idle_timeout reclaims
            that tail cheaply.
    """
    output_format = "stream-json" if stderr_log else "json"
    cmd = [
        "claude",
        "--print",
        "--output-format", output_format,
        "--max-turns", str(max_turns),
        "--dangerously-skip-permissions",
        # Isolation: prevent user's global MCP servers, plugins, and hooks
        # from affecting eval results. Only workspace-local settings load
        # (used for intent_layer hooks via .claude/settings.local.json).
        "--strict-mcp-config",
        "--setting-sources", "local",
    ]
    if stderr_log:
        cmd.append("--verbose")
    if model:
        cmd.extend(["--model", model])

    # Pass prompt via stdin instead of CLI argument to avoid hitting
    # macOS ARG_MAX (~1MB combined args+env). Failing test output from
    # large test suites can easily exceed this limit.
    # Claude CLI reads from stdin when no positional prompt is given.
    prompt_via_stdin = True

    # Small prompts can safely go as CLI args (faster, no pipe overhead)
    if len(prompt.encode("utf-8")) < 100_000:
        cmd.append(prompt)
        prompt_via_stdin = False

    env = {**os.environ, "CLAUDE_NO_TELEMETRY": "1"}
    # Allow running from within a Claude session (e.g. smoke tests)
    env.pop("CLAUDECODE", None)
    if extra_env:
        env.update(extra_env)

    start = time.time()

    # Fast path: no log file → simple subprocess.run with json format
    if not stderr_log:
        try:
            result = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                input=prompt if prompt_via_stdin else None,
            )
            elapsed = time.time() - start
            metrics = parse_claude_output(result.stdout)
            return ClaudeResult(
                exit_code=result.returncode,
                wall_clock_seconds=elapsed,
                input_tokens=metrics["input_tokens"],
                output_tokens=metrics["output_tokens"],
                tool_calls=metrics["tool_calls"],
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=False,
                cost_usd=metrics.get("cost_usd", 0),
                num_turns=metrics.get("num_turns", 0),
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            return ClaudeResult(
                exit_code=-1,
                wall_clock_seconds=elapsed,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                stdout="",
                stderr="Command timed out",
                timed_out=True,
            )

    # Streaming path: stream-json on stdout → parse events → write log
    log_path = Path(stderr_log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stream_events: list[dict] = []

    def _drain_stdout(stream, log_file):
        """Read stream-json stdout, write summaries to log, collect lines.

        Also records per-event arrival metadata (relative seconds since
        `start`) for downstream throughput analysis. The list is appended
        from this thread only, so no lock is needed.
        """
        for line in stream:
            stdout_lines.append(line)
            record, summary = _extract_stream_event(line, time.time() - start)
            if record is not None:
                stream_events.append(record)
            if summary:
                log_file.write(summary + "\n")
                log_file.flush()

    def _drain_stderr(stream, log_file):
        """Capture stderr and append to log file."""
        for line in stream:
            stderr_lines.append(line)
            log_file.write(f"[stderr] {line}")
            log_file.flush()

    try:
        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdin=subprocess.PIPE if prompt_via_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            # Feed prompt via stdin, then close to signal EOF
            if prompt_via_stdin:
                try:
                    proc.stdin.write(prompt)
                    proc.stdin.close()
                except BrokenPipeError:
                    pass  # process already exited

            out_reader = threading.Thread(
                target=_drain_stdout,
                args=(proc.stdout, log_file),
                daemon=True,
            )
            err_reader = threading.Thread(
                target=_drain_stderr,
                args=(proc.stderr, log_file),
                daemon=True,
            )
            out_reader.start()
            err_reader.start()

            # Wait for process. The helper enforces both the hard `timeout`
            # ceiling and the optional `idle_timeout` (no new stream events).
            kill_reason = _wait_for_proc(
                proc, start, timeout, idle_timeout, stream_events
            )

            out_reader.join(timeout=5)
            err_reader.join(timeout=5)
            elapsed = time.time() - start
            metrics = parse_stream_json_output(stdout_lines)

            if kill_reason == "idle":
                # Annotate stderr so operators can distinguish idle-kills
                # from hard timeouts in post-hoc analysis.
                note = (
                    f"Killed: no stream events for "
                    f"{idle_timeout:.0f}s (total {elapsed:.0f}s)"
                )
                stderr_text = (
                    "".join(stderr_lines)
                    + ("\n" if stderr_lines else "")
                    + note
                )
            elif kill_reason == "timeout":
                stderr_text = "".join(stderr_lines) or "Command timed out"
            else:
                stderr_text = "".join(stderr_lines)

            return ClaudeResult(
                exit_code=-1 if kill_reason else proc.returncode,
                wall_clock_seconds=elapsed,
                input_tokens=metrics["input_tokens"],
                output_tokens=metrics["output_tokens"],
                tool_calls=metrics["tool_calls"],
                stdout="".join(stdout_lines),
                stderr=stderr_text,
                timed_out=bool(kill_reason),
                cost_usd=metrics.get("cost_usd", 0),
                num_turns=metrics.get("num_turns", 0),
                stream_events=stream_events,
            )
    except OSError as e:
        elapsed = time.time() - start
        return ClaudeResult(
            exit_code=-1,
            wall_clock_seconds=elapsed,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            stdout="",
            stderr=f"Failed to start process: {e}",
            timed_out=False,
            stream_events=stream_events,
        )
