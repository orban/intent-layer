# tests/test_claude_runner.py
import pytest
import json
from unittest.mock import patch, MagicMock
from lib.claude_runner import run_claude, ClaudeResult, parse_claude_output


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
