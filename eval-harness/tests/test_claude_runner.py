# tests/test_claude_runner.py
import pytest
import json
from unittest.mock import patch, MagicMock
from lib.claude_runner import (
    run_claude,
    ClaudeResult,
    parse_claude_output,
    parse_stream_json_output,
    _summarize_stream_event,
    _extract_stream_event,
    _wait_for_proc,
)


def test_parse_claude_output_extracts_tokens():
    output = json.dumps({
        "result": "done",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 500
        },
        "tool_calls": [{"name": "Read"}, {"name": "Edit"}]
    })

    result = parse_claude_output(output)
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 500
    assert result["tool_calls"] == 2


def test_parse_claude_output_handles_missing_fields():
    output = json.dumps({"result": "done"})

    result = parse_claude_output(output)
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["tool_calls"] == 0


def test_parse_claude_output_handles_list_format():
    """Claude CLI can output a list of messages instead of a dict."""
    output = json.dumps([
        {
            "role": "user",
            "content": [{"type": "text", "text": "Fix the bug"}]
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/foo/bar.js"}},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/foo/bar.js"}}
            ],
            "usage": {"input_tokens": 500, "output_tokens": 200}
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "Done"}],
            "usage": {"input_tokens": 300, "output_tokens": 100}
        }
    ])

    result = parse_claude_output(output)
    assert result["input_tokens"] == 800  # 500 + 300
    assert result["output_tokens"] == 300  # 200 + 100
    assert result["tool_calls"] == 2


def test_parse_claude_output_handles_empty_list():
    output = json.dumps([])
    result = parse_claude_output(output)
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["tool_calls"] == 0


def test_parse_claude_output_falls_back_to_num_turns():
    """When tool_calls key is absent, fall back to num_turns."""
    output = json.dumps({
        "result": "done",
        "usage": {
            "input_tokens": 289000,
            "output_tokens": 1500,
            "cache_read_input_tokens": 50000,
        },
        "num_turns": 7,
        "total_cost_usd": 0.15,
    })

    result = parse_claude_output(output)
    assert result["input_tokens"] == 339000  # 289000 + 50000
    assert result["output_tokens"] == 1500
    assert result["tool_calls"] == 7  # falls back to num_turns
    assert result["num_turns"] == 7
    assert result["cost_usd"] == 0.15


@patch("lib.claude_runner.subprocess.run")
def test_run_claude_includes_model_flag(mock_run):
    """Test that model parameter adds --model flag to command."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({"usage": {}, "tool_calls": []}),
        stderr=""
    )

    run_claude("/tmp/workspace", "Fix the bug", model="claude-sonnet-4-5-20250929")

    cmd = mock_run.call_args[0][0]
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "claude-sonnet-4-5-20250929"
    # prompt should be last
    assert cmd[-1] == "Fix the bug"


@patch("lib.claude_runner.subprocess.run")
def test_run_claude_no_model_flag_by_default(mock_run):
    """Test that --model flag is absent when model is not provided."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({"usage": {}, "tool_calls": []}),
        stderr=""
    )

    run_claude("/tmp/workspace", "Fix the bug")

    cmd = mock_run.call_args[0][0]
    assert "--model" not in cmd


def test_run_claude_stream_json_logs_tool_calls(tmp_path):
    """Test that stderr_log with stream-json writes tool summaries to log file."""
    log_file = tmp_path / "test.log"

    # Simulate stream-json NDJSON lines on stdout
    assistant_event = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/work/src/main.py"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/work/src/main.py"}},
        ]}
    })
    result_event = json.dumps({
        "type": "result",
        "usage": {"input_tokens": 1000, "output_tokens": 500},
        "tool_calls": [{"name": "Read"}, {"name": "Edit"}],
        "total_cost_usd": 0.05,
        "num_turns": 3,
    })
    stdout_lines = [assistant_event + "\n", result_event + "\n"]

    with patch("lib.claude_runner.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout.__iter__ = lambda self: iter(stdout_lines)
        mock_proc.stderr.__iter__ = lambda self: iter([])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        result = run_claude("/tmp/workspace", "Fix the bug", stderr_log=str(log_file))

    assert result.exit_code == 0
    assert result.tool_calls == 2
    assert result.input_tokens == 1000
    assert result.cost_usd == 0.05
    # Log file should contain tool call summaries
    log_content = log_file.read_text()
    assert "Read" in log_content
    assert "Edit" in log_content
    assert "[result]" in log_content


def test_run_claude_stream_json_timeout_preserves_partial(tmp_path, monkeypatch):
    """stream-json path preserves partial metrics when hard timeout fires."""
    log_file = tmp_path / "timeout.log"

    # One assistant event before timeout
    assistant_event = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
        ]}
    })

    # Fake time progression: start at 0, jump past the 5s deadline on the next
    # check. The _wait_for_proc loop reads time.time() once per poll, so we
    # need enough ticks to cover: start stamp, the loop check, the elapsed
    # calc after return, plus some slack.
    times = iter([0.0, 0.0] + [6.0] * 20)
    monkeypatch.setattr("lib.claude_runner.time.time", lambda: next(times))
    monkeypatch.setattr("lib.claude_runner.time.sleep", lambda _s: None)

    with patch("lib.claude_runner.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = lambda self: iter([assistant_event + "\n"])
        mock_proc.stderr.__iter__ = lambda self: iter([])
        mock_proc.poll.return_value = None  # still running — forces timeout branch
        mock_proc.kill.return_value = None
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        result = run_claude("/tmp/workspace", "Fix the bug", timeout=5, stderr_log=str(log_file))

    assert result.timed_out is True
    # Should have counted the one tool call from partial output
    assert result.tool_calls == 1
    # Log file should have the tool summary
    assert "Bash" in log_file.read_text()


def test_run_claude_stream_json_uses_correct_format(tmp_path):
    """Test that stderr_log triggers stream-json format in the command."""
    log_file = tmp_path / "test.log"
    result_event = json.dumps({
        "type": "result",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    })

    with patch("lib.claude_runner.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout.__iter__ = lambda self: iter([result_event + "\n"])
        mock_proc.stderr.__iter__ = lambda self: iter([])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        run_claude("/tmp/workspace", "Fix the bug", stderr_log=str(log_file))

    cmd = mock_popen.call_args[0][0]
    fmt_idx = cmd.index("--output-format")
    assert cmd[fmt_idx + 1] == "stream-json"
    assert "--verbose" in cmd


# --- Unit tests for stream-json helpers ---


def test_summarize_stream_event_tool_use():
    """Test that _summarize_stream_event extracts tool names."""
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/work/foo.py"}},
        ]}
    })
    summary = _summarize_stream_event(line)
    assert summary is not None
    assert "Read" in summary
    assert "foo.py" in summary


def test_summarize_stream_event_result():
    """Test that _summarize_stream_event formats result events."""
    line = json.dumps({
        "type": "result",
        "num_turns": 5,
        "total_cost_usd": 0.123,
    })
    summary = _summarize_stream_event(line)
    assert "[result]" in summary
    assert "5 turns" in summary


def test_summarize_stream_event_ignores_system():
    """Test that _summarize_stream_event returns None for system events."""
    line = json.dumps({"type": "system", "subtype": "init"})
    assert _summarize_stream_event(line) is None


def test_extract_stream_event_assistant_with_tool_and_usage():
    """Assistant event records arrival time, tool names, and token deltas."""
    line = json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "thinking..."},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
            ],
            "usage": {
                "input_tokens": 4,
                "output_tokens": 120,
                "cache_read_input_tokens": 18000,
                "cache_creation_input_tokens": 250,
            },
        },
    })
    record, summary = _extract_stream_event(line, t=12.345)
    assert record is not None
    assert record["t"] == 12.345
    assert record["type"] == "assistant"
    assert record["tools"] == ["Bash"]
    assert record["inp"] == 4
    assert record["out"] == 120
    assert record["cache_read"] == 18000
    assert record["cache_create"] == 250
    assert summary is not None and "Bash" in summary


def test_extract_stream_event_assistant_text_only():
    """Assistant text-only event records timestamp + type but no tools, no summary."""
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "ok"}], "usage": {"output_tokens": 3}},
    })
    record, summary = _extract_stream_event(line, t=1.0)
    assert record is not None
    assert record["type"] == "assistant"
    assert "tools" not in record
    assert record["out"] == 3
    assert summary is None


def test_extract_stream_event_result_captures_cost_and_turns():
    line = json.dumps({"type": "result", "num_turns": 7, "total_cost_usd": 0.42})
    record, summary = _extract_stream_event(line, t=99.0)
    assert record is not None
    assert record["type"] == "result"
    assert record["num_turns"] == 7
    assert record["cost_usd"] == 0.42
    assert summary is not None and "[result]" in summary and "7 turns" in summary


def test_extract_stream_event_user_event_records_timestamp():
    """User events (tool_result) get a timestamp record but no summary line."""
    line = json.dumps({"type": "user", "message": {"content": []}})
    record, summary = _extract_stream_event(line, t=5.5)
    assert record == {"t": 5.5, "type": "user"}
    assert summary is None


def test_extract_stream_event_unparseable_returns_none_pair():
    record, summary = _extract_stream_event("not json", t=0.0)
    assert record is None
    assert summary is None


def test_parse_stream_json_output_with_result():
    """Test parsing NDJSON with a result event."""
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {}},
        ]}}) + "\n",
        json.dumps({"type": "result", "usage": {
            "input_tokens": 2000, "output_tokens": 800,
            "cache_read_input_tokens": 500,
        }, "num_turns": 4, "total_cost_usd": 0.10}) + "\n",
    ]
    metrics = parse_stream_json_output(lines)
    assert metrics["input_tokens"] == 2500  # 2000 + 500
    assert metrics["output_tokens"] == 800
    assert metrics["num_turns"] == 4
    assert metrics["cost_usd"] == 0.10


def test_parse_stream_json_output_no_result_fallback():
    """Test parsing NDJSON without a result event falls back to counting."""
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "tool_use", "name": "Edit", "input": {}},
        ]}}) + "\n",
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {}},
        ]}}) + "\n",
    ]
    metrics = parse_stream_json_output(lines)
    assert metrics["tool_calls"] == 3
    assert metrics["input_tokens"] == 0  # no result event → zero


def test_parse_stream_json_output_empty():
    """Test parsing empty NDJSON."""
    assert parse_stream_json_output([])["tool_calls"] == 0


def test_claude_result_dataclass():
    result = ClaudeResult(
        exit_code=0,
        wall_clock_seconds=45.2,
        input_tokens=1000,
        output_tokens=500,
        tool_calls=5,
        stdout="output",
        stderr="",
        timed_out=False
    )
    assert result.exit_code == 0
    assert result.wall_clock_seconds == 45.2


# --- _wait_for_proc watchdog ---


class _FakeProc:
    """Mimics subprocess.Popen surface needed by _wait_for_proc.

    `poll_sequence` is a list of values returned by successive poll() calls.
    None means still-running; an int means the process exited with that code.
    kill() advances to the next sequence entry so the loop sees it exit.
    """

    def __init__(self, poll_sequence: list):
        self._seq = list(poll_sequence)
        self._calls = 0
        self.kill_called = False
        self.wait_called = False

    def poll(self):
        if self._calls < len(self._seq):
            v = self._seq[self._calls]
            self._calls += 1
            return v
        return self._seq[-1]

    def kill(self):
        self.kill_called = True
        # After kill, the next poll should show exit. Append a "killed" code
        # at the end so poll() returns non-None on subsequent calls.
        self._seq.append(-9)

    def wait(self):
        self.wait_called = True


def test_wait_for_proc_returns_none_when_proc_exits_on_own(monkeypatch):
    """Process exits normally → returns None, no kill."""
    # Bypass real sleep and pin wall-clock before the hard deadline.
    monkeypatch.setattr("lib.claude_runner.time.sleep", lambda _s: None)
    monkeypatch.setattr("lib.claude_runner.time.time", lambda: 1.0)
    proc = _FakeProc(poll_sequence=[None, 0])  # running, then exited
    reason = _wait_for_proc(proc, start=0.0, timeout=60, idle_timeout=None,
                            stream_events=[], poll_interval=0.01)
    assert reason is None
    assert not proc.kill_called


def test_wait_for_proc_kills_on_hard_timeout(monkeypatch):
    """now >= deadline → kill with reason 'timeout'."""
    # Fake time.time progression: 0.0 (start), 61.0 (past deadline).
    ticks = iter([0.0, 61.0, 61.0, 61.0])
    monkeypatch.setattr("lib.claude_runner.time.time", lambda: next(ticks))
    monkeypatch.setattr("lib.claude_runner.time.sleep", lambda _s: None)
    proc = _FakeProc(poll_sequence=[None])
    reason = _wait_for_proc(proc, start=0.0, timeout=60, idle_timeout=None,
                            stream_events=[], poll_interval=0.01)
    assert reason == "timeout"
    assert proc.kill_called and proc.wait_called


def test_wait_for_proc_kills_on_idle(monkeypatch):
    """No stream events for idle_timeout → kill with reason 'idle'."""
    ticks = iter([30.0, 30.0, 30.0])  # 30s since start, no events
    monkeypatch.setattr("lib.claude_runner.time.time", lambda: next(ticks))
    monkeypatch.setattr("lib.claude_runner.time.sleep", lambda _s: None)
    proc = _FakeProc(poll_sequence=[None])
    reason = _wait_for_proc(proc, start=0.0, timeout=600, idle_timeout=20,
                            stream_events=[], poll_interval=0.01)
    assert reason == "idle"
    assert proc.kill_called


def test_wait_for_proc_does_not_kill_when_events_are_fresh(monkeypatch):
    """Recent stream event → not idle, proc continues until it exits on own."""
    monkeypatch.setattr("lib.claude_runner.time.time", lambda: 30.0)
    monkeypatch.setattr("lib.claude_runner.time.sleep", lambda _s: None)
    proc = _FakeProc(poll_sequence=[None, 0])  # running, then exits clean
    # Event arrived at t=29.0 relative — only 1s before our check at wall=30.0
    events = [{"t": 29.0, "type": "assistant"}]
    reason = _wait_for_proc(proc, start=0.0, timeout=600, idle_timeout=20,
                            stream_events=events, poll_interval=0.01)
    assert reason is None
    assert not proc.kill_called


def test_wait_for_proc_idle_timeout_disabled_when_zero_or_none(monkeypatch):
    """idle_timeout=None or 0 → no idle check, only hard timeout applies."""
    monkeypatch.setattr("lib.claude_runner.time.time", lambda: 50.0)
    monkeypatch.setattr("lib.claude_runner.time.sleep", lambda _s: None)
    proc = _FakeProc(poll_sequence=[None, 0])
    # 50s into a 60s timeout, no events — would trip any positive idle threshold
    reason = _wait_for_proc(proc, start=0.0, timeout=60, idle_timeout=0,
                            stream_events=[], poll_interval=0.01)
    assert reason is None
    assert not proc.kill_called
