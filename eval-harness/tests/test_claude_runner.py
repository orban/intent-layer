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
