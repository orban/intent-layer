# tests/test_prompt_builder.py
import pytest
from lib.prompt_builder import (
    build_prompt_from_commit_message,
    build_prompt_from_failing_test,
    AGENTS_MD_PREAMBLE,
)
from lib.models import Task


def test_build_prompt_from_commit_message():
    prompt = build_prompt_from_commit_message("fix: handle null pointer in middleware")

    assert "fix: handle null pointer in middleware" in prompt
    assert "Fix the following bug" in prompt
    assert "tests pass" in prompt.lower()
    # Without preamble by default
    assert "AGENTS.md" not in prompt


def test_build_prompt_from_commit_message_with_preamble():
    prompt = build_prompt_from_commit_message(
        "fix: handle null pointer", with_agents_preamble=True
    )

    assert "fix: handle null pointer" in prompt
    assert "AGENTS.md" in prompt
    assert "pitfalls to avoid" in prompt
    assert "contracts" in prompt


def test_build_prompt_from_failing_test():
    test_output = "AssertionError: expected 200 but got 500"
    prompt = build_prompt_from_failing_test(test_output)

    assert "AssertionError" in prompt
    assert "failing" in prompt.lower()
    assert "Do not modify the test" in prompt
    # Without preamble by default
    assert "AGENTS.md" not in prompt


def test_build_prompt_from_failing_test_with_preamble():
    test_output = "AssertionError: expected 200 but got 500"
    prompt = build_prompt_from_failing_test(test_output, with_agents_preamble=True)

    assert "AssertionError" in prompt
    assert "AGENTS.md" in prompt
    assert "pitfalls to avoid" in prompt
