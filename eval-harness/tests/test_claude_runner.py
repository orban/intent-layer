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


def test_run_claude_stream_json_timeout_preserves_partial(tmp_path):
    """Test that stream-json path preserves partial metrics on timeout."""
    import subprocess
    log_file = tmp_path / "timeout.log"

    # One assistant event before timeout
    assistant_event = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
        ]}
    })

    with patch("lib.claude_runner.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = lambda self: iter([assistant_event + "\n"])
        mock_proc.stderr.__iter__ = lambda self: iter([])
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="claude", timeout=5),
            None,
        ]
        mock_proc.kill.return_value = None
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
