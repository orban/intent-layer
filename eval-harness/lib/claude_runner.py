# lib/claude_runner.py
from __future__ import annotations
import subprocess
import time
import json
import os
from dataclasses import dataclass


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

        # Handle dict output (single response with aggregated stats)
        if isinstance(data, dict):
            usage = data.get("usage", {})
            tools = data.get("tool_calls", [])
            return {
                "input_tokens": usage.get("input_tokens", 0) if isinstance(usage, dict) else 0,
                "output_tokens": usage.get("output_tokens", 0) if isinstance(usage, dict) else 0,
                "tool_calls": len(tools) if isinstance(tools, list) else 0
            }

        return {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0}
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0}


def run_claude(
    workspace: str,
    prompt: str,
    timeout: int = 300,
    max_turns: int = 50,
    model: str | None = None
) -> ClaudeResult:
    """Run Claude Code CLI and capture metrics."""
    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--max-turns", str(max_turns),
        "--dangerously-skip-permissions",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    env = {**os.environ, "CLAUDE_NO_TELEMETRY": "1"}
    # Allow running from within a Claude session (e.g. smoke tests)
    env.pop("CLAUDECODE", None)

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
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
            timed_out=False
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
            timed_out=True
        )
