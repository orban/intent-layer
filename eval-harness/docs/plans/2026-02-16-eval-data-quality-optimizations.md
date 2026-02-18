# Eval data quality optimizations

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix four data quality problems surfaced by analyzing eval output: empty-run detection, timeout tagging, Claude exit code capture, and stale success delta key.

**Architecture:** All changes are additive. TaskResult gets two new optional fields (`exit_code`, `is_timeout`). The `run()` method detects empty runs and timeouts, tagging them with new error prefixes. Reporter learns to recognize the new error tags. No changes to CLI, cache, or prompt builder.

**Tech Stack:** Python, pytest, dataclasses, existing eval harness modules

---

### Task 1: Add `exit_code` and `is_timeout` to TaskResult

**Files:**
- Modify: `eval-harness/lib/task_runner.py:50-63` (TaskResult dataclass)
- Test: `eval-harness/tests/test_task_runner.py`

**Step 1: Write the failing test**

```python
def test_task_result_has_exit_code_and_timeout():
    """TaskResult supports exit_code and is_timeout fields."""
    result = TaskResult(
        task_id="fix-meta",
        condition=Condition.NONE,
        success=False,
        test_output="",
        wall_clock_seconds=300.0,
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        lines_changed=0,
        files_touched=[],
        exit_code=1,
        is_timeout=True,
    )
    assert result.exit_code == 1
    assert result.is_timeout is True


def test_task_result_defaults_exit_code_and_timeout():
    """exit_code defaults to None, is_timeout defaults to False."""
    result = TaskResult(
        task_id="fix-defaults",
        condition=Condition.NONE,
        success=True,
        test_output="PASS",
        wall_clock_seconds=50.0,
        input_tokens=2000,
        output_tokens=1000,
        tool_calls=10,
        lines_changed=20,
        files_touched=["a.py"],
    )
    assert result.exit_code is None
    assert result.is_timeout is False
```

**Step 2: Run tests to verify they fail**

Run: `cd eval-harness && uv run pytest tests/test_task_runner.py::test_task_result_has_exit_code_and_timeout tests/test_task_runner.py::test_task_result_defaults_exit_code_and_timeout -v`
Expected: FAIL with "unexpected keyword argument 'exit_code'"

**Step 3: Add the fields to TaskResult**

In `eval-harness/lib/task_runner.py`, add to the TaskResult dataclass after line 63 (`error`):

```python
    exit_code: int | None = None
    is_timeout: bool = False
```

**Step 4: Run tests to verify they pass**

Run: `cd eval-harness && uv run pytest tests/test_task_runner.py::test_task_result_has_exit_code_and_timeout tests/test_task_runner.py::test_task_result_defaults_exit_code_and_timeout -v`
Expected: PASS

**Step 5: Run full test suite to check nothing broke**

Run: `cd eval-harness && uv run pytest tests/ -v`
Expected: All 120 tests PASS (new fields have defaults, no existing code breaks)

**Step 6: Commit**

```bash
git add eval-harness/lib/task_runner.py eval-harness/tests/test_task_runner.py
git commit -m "feat: add exit_code and is_timeout fields to TaskResult"
```

---

### Task 2: Detect empty runs in `run()`

An "empty run" is when Claude starts but produces nothing: `wall_clock_seconds > 1` but `input_tokens == 0 and output_tokens == 0 and not timed_out`. This happens when the Claude CLI errors on startup (exit code != 0) without processing any tokens. These should be tagged `[empty-run]` and excluded from stats.

**Files:**
- Modify: `eval-harness/lib/task_runner.py:486-531` (the section after `run_claude` returns, before the `return TaskResult`)
- Test: `eval-harness/tests/test_task_runner.py`

**Step 1: Write the failing test**

```python
def test_empty_run_detection():
    """A result with >1s wall clock but 0 tokens is an empty run."""
    from lib.reporter import Reporter

    result = TaskResult(
        task_id="fix-empty",
        condition=Condition.INTENT_LAYER,
        success=False,
        test_output="",
        wall_clock_seconds=2.7,
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        lines_changed=0,
        files_touched=[],
        error="[empty-run] Claude produced no output (exit_code=1, 2.7s)",
        exit_code=1,
    )
    # Empty runs are infra errors — excluded from success stats
    assert Reporter._is_infra_error(result) is True


def test_empty_run_tag_format():
    """Verify the [empty-run] tag is recognized by _is_infra_error."""
    from lib.reporter import Reporter

    result = TaskResult(
        task_id="fix-emp",
        condition=Condition.NONE,
        success=False,
        test_output="",
        wall_clock_seconds=3.0,
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        lines_changed=0,
        files_touched=[],
        error="[empty-run] Claude produced no output (exit_code=0, 3.0s)",
    )
    assert Reporter._is_infra_error(result) is True
```

**Step 2: Run tests to verify they fail**

Run: `cd eval-harness && uv run pytest tests/test_task_runner.py::test_empty_run_detection tests/test_task_runner.py::test_empty_run_tag_format -v`
Expected: FAIL — `_is_infra_error` doesn't recognize `[empty-run]` yet

**Step 3: Add `[empty-run]` to Reporter._is_infra_error**

In `eval-harness/lib/reporter.py`, modify `_is_infra_error` (line 246):

Change:
```python
        return r.error.startswith(("[infrastructure]", "[pre-validation]", "[skill-generation]"))
```
To:
```python
        return r.error.startswith(("[infrastructure]", "[pre-validation]", "[skill-generation]", "[empty-run]"))
```

**Step 4: Run tests to verify they pass**

Run: `cd eval-harness && uv run pytest tests/test_task_runner.py::test_empty_run_detection tests/test_task_runner.py::test_empty_run_tag_format -v`
Expected: PASS

**Step 5: Add empty-run detection logic in `run()`**

In `eval-harness/lib/task_runner.py`, after the `run_claude` call (around line 492, after `self._progress(task.id, cond_str, "claude_done", ...)`), add:

```python
            # Detect empty runs: Claude started but produced nothing
            if (claude_result.wall_clock_seconds > 1
                    and claude_result.input_tokens == 0
                    and claude_result.output_tokens == 0
                    and not claude_result.timed_out):
                return TaskResult(
                    task_id=task.id,
                    condition=condition,
                    success=False,
                    test_output="",
                    wall_clock_seconds=claude_result.wall_clock_seconds,
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls=0,
                    lines_changed=0,
                    files_touched=[],
                    error=(
                        f"[empty-run] Claude produced no output "
                        f"(exit_code={claude_result.exit_code}, "
                        f"{claude_result.wall_clock_seconds:.1f}s)"
                    ),
                    exit_code=claude_result.exit_code,
                )
```

Also update the normal success return (line ~518-531) to include exit_code:

```python
            return TaskResult(
                task_id=task.id,
                condition=condition,
                success=test_result.exit_code == 0,
                test_output=test_result.stdout + test_result.stderr,
                wall_clock_seconds=claude_result.wall_clock_seconds,
                input_tokens=claude_result.input_tokens,
                output_tokens=claude_result.output_tokens,
                tool_calls=claude_result.tool_calls,
                lines_changed=diff_stats.lines_changed,
                files_touched=diff_stats.files,
                skill_generation=skill_metrics,
                agents_files_read=agents_files_read,
                exit_code=claude_result.exit_code,
            )
```

**Step 6: Run full test suite**

Run: `cd eval-harness && uv run pytest tests/ -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add eval-harness/lib/task_runner.py eval-harness/lib/reporter.py eval-harness/tests/test_task_runner.py
git commit -m "feat: detect and tag empty Claude runs as [empty-run]"
```

---

### Task 3: Detect and tag timeout failures

When `claude_result.timed_out` is True, the current code runs tests anyway (which usually fail because nothing was done). These should be tagged `[timeout]` so they're distinguishable from "Claude tried and tests didn't pass."

**Files:**
- Modify: `eval-harness/lib/task_runner.py:486-495` (after run_claude, before test run)
- Modify: `eval-harness/lib/reporter.py:246` (_is_infra_error)
- Test: `eval-harness/tests/test_task_runner.py`

**Step 1: Write the failing test**

```python
def test_timeout_tag_is_infra_error():
    """[timeout] errors are excluded from success stats."""
    from lib.reporter import Reporter

    result = TaskResult(
        task_id="fix-timeout",
        condition=Condition.FLAT_LLM,
        success=False,
        test_output="",
        wall_clock_seconds=300.0,
        input_tokens=50000,
        output_tokens=3000,
        tool_calls=5,
        lines_changed=0,
        files_touched=[],
        error="[timeout] Claude timed out after 300.0s",
        is_timeout=True,
    )
    assert Reporter._is_infra_error(result) is True
```

**Step 2: Run test to verify it fails**

Run: `cd eval-harness && uv run pytest tests/test_task_runner.py::test_timeout_tag_is_infra_error -v`
Expected: FAIL — `_is_infra_error` doesn't know `[timeout]`

**Step 3: Add `[timeout]` to Reporter._is_infra_error**

In `eval-harness/lib/reporter.py`, modify `_is_infra_error` (line 246):

Change:
```python
        return r.error.startswith(("[infrastructure]", "[pre-validation]", "[skill-generation]", "[empty-run]"))
```
To:
```python
        return r.error.startswith(("[infrastructure]", "[pre-validation]", "[skill-generation]", "[empty-run]", "[timeout]"))
```

**Step 4: Run test to verify it passes**

Run: `cd eval-harness && uv run pytest tests/test_task_runner.py::test_timeout_tag_is_infra_error -v`
Expected: PASS

**Step 5: Add timeout detection in `run()`**

In `eval-harness/lib/task_runner.py`, after `run_claude` returns and after the empty-run check, add:

```python
            # Detect timeout: Claude ran out of time
            if claude_result.timed_out:
                return TaskResult(
                    task_id=task.id,
                    condition=condition,
                    success=False,
                    test_output="",
                    wall_clock_seconds=claude_result.wall_clock_seconds,
                    input_tokens=claude_result.input_tokens,
                    output_tokens=claude_result.output_tokens,
                    tool_calls=claude_result.tool_calls,
                    lines_changed=0,
                    files_touched=[],
                    error=(
                        f"[timeout] Claude timed out after "
                        f"{claude_result.wall_clock_seconds:.1f}s"
                    ),
                    exit_code=claude_result.exit_code,
                    is_timeout=True,
                )
```

**Step 6: Run full test suite**

Run: `cd eval-harness && uv run pytest tests/ -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add eval-harness/lib/task_runner.py eval-harness/lib/reporter.py eval-harness/tests/test_task_runner.py
git commit -m "feat: detect and tag Claude timeouts as [timeout]"
```

---

### Task 4: Serialize new fields in reporter output

The reporter should include `exit_code`, `is_timeout`, and the error tag in JSON output for post-hoc analysis.

**Files:**
- Modify: `eval-harness/lib/reporter.py:73-117` (_serialize_single_result)
- Test: `eval-harness/tests/test_reporter.py`

**Step 1: Write the failing test**

```python
def test_serialize_includes_exit_code_and_timeout():
    """JSON output includes exit_code and is_timeout when present."""
    reporter = Reporter(output_dir="/tmp")

    result = TaskResult(
        task_id="fix-meta",
        condition=Condition.NONE,
        success=False,
        test_output="FAIL",
        wall_clock_seconds=300.0,
        input_tokens=50000,
        output_tokens=3000,
        tool_calls=5,
        lines_changed=0,
        files_touched=[],
        error="[timeout] Claude timed out after 300.0s",
        exit_code=-1,
        is_timeout=True,
    )

    serialized = reporter._serialize_single_result(result)

    assert serialized["exit_code"] == -1
    assert serialized["is_timeout"] is True
    assert serialized["error"] == "[timeout] Claude timed out after 300.0s"


def test_serialize_omits_exit_code_when_none():
    """JSON output omits exit_code when it's None (backward compat)."""
    reporter = Reporter(output_dir="/tmp")

    result = TaskResult(
        task_id="fix-ok",
        condition=Condition.NONE,
        success=True,
        test_output="PASS",
        wall_clock_seconds=50.0,
        input_tokens=2000,
        output_tokens=1000,
        tool_calls=10,
        lines_changed=20,
        files_touched=["a.py"],
    )

    serialized = reporter._serialize_single_result(result)

    assert "exit_code" not in serialized
    assert "is_timeout" not in serialized
```

**Step 2: Run tests to verify they fail**

Run: `cd eval-harness && uv run pytest tests/test_reporter.py::test_serialize_includes_exit_code_and_timeout tests/test_reporter.py::test_serialize_omits_exit_code_when_none -v`
Expected: FAIL — exit_code and is_timeout not in output

**Step 3: Update _serialize_single_result**

In `eval-harness/lib/reporter.py`, at the end of `_serialize_single_result`, before `return result` (around line 116-117), add:

```python
        if r.exit_code is not None:
            result["exit_code"] = r.exit_code
        if r.is_timeout:
            result["is_timeout"] = r.is_timeout
```

**Step 4: Run tests to verify they pass**

Run: `cd eval-harness && uv run pytest tests/test_reporter.py::test_serialize_includes_exit_code_and_timeout tests/test_reporter.py::test_serialize_omits_exit_code_when_none -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `cd eval-harness && uv run pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add eval-harness/lib/reporter.py eval-harness/tests/test_reporter.py
git commit -m "feat: serialize exit_code and is_timeout in JSON output"
```

---

### Task 5: Clean up stale single-run `success` delta key

The old code emits `"success": "+0"` for single-run deltas, which is always +0 or +1 and not useful. It was already renamed to `success_rate_delta` in the multi-run code but might still show `+0`/`+1` for single runs. That's fine (it's technically correct), but we should verify it works correctly end-to-end and make sure the markdown renderer doesn't display meaningless +0 deltas.

This is actually just a verification task. Looking at the code, `_compute_delta` already emits `success_rate_delta` for both single and multi-run. The markdown renderer doesn't display it. No code change needed — just confirm with a test.

**Files:**
- Test: `eval-harness/tests/test_reporter.py`

**Step 1: Write verification test**

```python
def test_single_run_delta_uses_success_rate_delta_key():
    """Single-run deltas use 'success_rate_delta' (not 'success')."""
    reporter = Reporter(output_dir="/tmp")

    baseline = [TaskResult(
        task_id="fix-key", condition=Condition.NONE, success=False,
        test_output="FAIL", wall_clock_seconds=100.0,
        input_tokens=5000, output_tokens=2000, tool_calls=20,
        lines_changed=50, files_touched=["a.py"]
    )]
    treatment = [TaskResult(
        task_id="fix-key", condition=Condition.FLAT_LLM, success=True,
        test_output="PASS", wall_clock_seconds=80.0,
        input_tokens=4000, output_tokens=1500, tool_calls=15,
        lines_changed=30, files_touched=["a.py"]
    )]

    delta = reporter._compute_delta(baseline, treatment)

    # Key must be success_rate_delta, not the old "success"
    assert "success_rate_delta" in delta
    assert "success" not in delta
    assert delta["success_rate_delta"] == "+1"
```

**Step 2: Run the test**

Run: `cd eval-harness && uv run pytest tests/test_reporter.py::test_single_run_delta_uses_success_rate_delta_key -v`
Expected: PASS (already correct)

**Step 3: Commit**

```bash
git add eval-harness/tests/test_reporter.py
git commit -m "test: verify single-run delta uses success_rate_delta key"
```

---

## Summary of changes

| File | What changes |
|------|-------------|
| `lib/task_runner.py` | TaskResult gets `exit_code` and `is_timeout` fields. `run()` detects empty runs and timeouts before running tests. |
| `lib/reporter.py` | `_is_infra_error` recognizes `[empty-run]` and `[timeout]`. `_serialize_single_result` includes new fields in JSON. |
| `tests/test_task_runner.py` | 5 new tests: field defaults, empty-run detection, empty-run tag, timeout tag, exit code capture. |
| `tests/test_reporter.py` | 3 new tests: serialize exit_code/timeout, omit when absent, delta key verification. |

## What's NOT in scope

- **Context file filtering in diff stats** — already implemented in `get_diff_stats()` with `exclude_context_files=True` default. The old results showing inflated `files_touched` were generated before that code existed.
- **CLI changes** — no changes needed; the CLI just passes through TaskResults.
- **Cache changes** — no changes needed.
