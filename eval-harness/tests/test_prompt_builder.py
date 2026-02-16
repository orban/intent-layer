# tests/test_prompt_builder.py
import pytest
from lib.prompt_builder import (
    build_prompt_from_commit_message,
    build_prompt_from_failing_test,
    build_flat_generation_prompt,
    FLAT_PREAMBLE,
    INTENT_LAYER_PREAMBLE,
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
        "fix: handle null pointer", preamble=INTENT_LAYER_PREAMBLE
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
    prompt = build_prompt_from_failing_test(test_output, preamble=INTENT_LAYER_PREAMBLE)

    assert "AssertionError" in prompt
    assert "AGENTS.md" in prompt
    assert "pitfalls to avoid" in prompt


def test_flat_preamble_content():
    assert "CLAUDE.md" in FLAT_PREAMBLE
    assert "tests" in FLAT_PREAMBLE.lower()


def test_intent_layer_preamble_content():
    assert "AGENTS.md" in INTENT_LAYER_PREAMBLE
    assert "pitfalls" in INTENT_LAYER_PREAMBLE
    assert "contracts" in INTENT_LAYER_PREAMBLE


def test_flat_generation_prompt():
    prompt = build_flat_generation_prompt()
    assert "analyze this codebase" in prompt
    assert "CLAUDE.md" in prompt
    assert "high-level code architecture" in prompt.lower()
    assert "init_planner" not in prompt  # implementation detail should not leak


def test_no_preamble_by_default():
    prompt = build_prompt_from_commit_message("fix: some bug")
    # Should start directly with "Fix the following bug"
    assert prompt.startswith("Fix the following bug")
