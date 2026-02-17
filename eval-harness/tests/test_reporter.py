# tests/test_reporter.py
import pytest
import json
from pathlib import Path
from lib.reporter import Reporter, EvalResults
from lib.task_runner import TaskResult, Condition, SkillGenerationMetrics


@pytest.fixture
def three_condition_results():
    return [
        TaskResult(
            task_id="fix-123",
            condition=Condition.NONE,
            success=False,
            test_output="FAIL",
            wall_clock_seconds=100.0,
            input_tokens=5000,
            output_tokens=2000,
            tool_calls=20,
            lines_changed=50,
            files_touched=["a.py", "b.py"]
        ),
        TaskResult(
            task_id="fix-123",
            condition=Condition.FLAT_LLM,
            success=True,
            test_output="PASS",
            wall_clock_seconds=80.0,
            input_tokens=4000,
            output_tokens=1500,
            tool_calls=15,
            lines_changed=30,
            files_touched=["a.py"],
            skill_generation=SkillGenerationMetrics(
                wall_clock_seconds=20.0,
                input_tokens=1000,
                output_tokens=300
            )
        ),
        TaskResult(
            task_id="fix-123",
            condition=Condition.INTENT_LAYER,
            success=True,
            test_output="PASS",
            wall_clock_seconds=60.0,
            input_tokens=3000,
            output_tokens=1000,
            tool_calls=10,
            lines_changed=25,
            files_touched=["a.py"],
            skill_generation=SkillGenerationMetrics(
                wall_clock_seconds=30.0,
                input_tokens=2000,
                output_tokens=500
            )
        ),
    ]


def test_three_condition_compilation(three_condition_results):
    """All three conditions present — none, flat_llm, intent_layer."""
    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(three_condition_results)

    assert len(eval_results.results) == 1
    task = eval_results.results[0]

    assert task["task_id"] == "fix-123"
    assert task["none"] is not None
    assert task["flat_llm"] is not None
    assert task["intent_layer"] is not None

    # none should be flat structure (no skill_generation)
    assert task["none"]["success"] is False
    assert task["none"]["wall_clock_seconds"] == 100.0
    assert "fix_only" not in task["none"]

    # flat_llm should have three-level structure
    assert task["flat_llm"]["success"] is True
    assert "fix_only" in task["flat_llm"]
    assert task["flat_llm"]["fix_only"]["wall_clock_seconds"] == 80.0

    # intent_layer should have three-level structure
    assert task["intent_layer"]["success"] is True
    assert "fix_only" in task["intent_layer"]
    assert task["intent_layer"]["fix_only"]["wall_clock_seconds"] == 60.0


def test_deltas_relative_to_none(three_condition_results):
    """Both flat_llm and intent_layer get deltas against the none baseline."""
    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(three_condition_results)

    task = eval_results.results[0]
    deltas = task["deltas"]

    # flat_llm delta: time (80 - 100) / 100 = -20%
    assert deltas["flat_llm"]["time_percent"] == "-20.0%"
    # flat_llm delta: tokens (5500 - 7000) / 7000 = -21.4%
    assert deltas["flat_llm"]["tokens_percent"] == "-21.4%"
    # flat_llm delta: success +1 (True - False), single run format
    assert deltas["flat_llm"]["success_rate_delta"] == "+1"

    # intent_layer delta: time (60 - 100) / 100 = -40%
    assert deltas["intent_layer"]["time_percent"] == "-40.0%"
    # intent_layer delta: tokens (4000 - 7000) / 7000 = -42.9%
    assert deltas["intent_layer"]["tokens_percent"] == "-42.9%"
    assert deltas["intent_layer"]["success_rate_delta"] == "+1"


def test_zero_baseline_delta():
    """If none has 0 time/tokens, don't divide by zero."""
    results = [
        TaskResult(
            task_id="fix-zero",
            condition=Condition.NONE,
            success=False,
            test_output="FAIL",
            wall_clock_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[]
        ),
        TaskResult(
            task_id="fix-zero",
            condition=Condition.FLAT_LLM,
            success=True,
            test_output="PASS",
            wall_clock_seconds=50.0,
            input_tokens=3000,
            output_tokens=1000,
            tool_calls=10,
            lines_changed=20,
            files_touched=["a.py"],
            skill_generation=SkillGenerationMetrics(
                wall_clock_seconds=10.0,
                input_tokens=500,
                output_tokens=100
            )
        ),
    ]

    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(results)

    task = eval_results.results[0]
    delta = task["deltas"]["flat_llm"]

    # Should not raise ZeroDivisionError; uses 0 fallback
    assert delta["time_percent"] == "+0.0%"
    assert delta["tokens_percent"] == "+0.0%"
    assert delta["tool_calls_percent"] == "+0.0%"
    assert delta["lines_changed_percent"] == "+0.0%"


def test_missing_condition():
    """Only 2 of 3 conditions run — missing one is None."""
    results = [
        TaskResult(
            task_id="fix-partial",
            condition=Condition.NONE,
            success=True,
            test_output="PASS",
            wall_clock_seconds=90.0,
            input_tokens=4000,
            output_tokens=1500,
            tool_calls=18,
            lines_changed=40,
            files_touched=["x.py"]
        ),
        TaskResult(
            task_id="fix-partial",
            condition=Condition.INTENT_LAYER,
            success=True,
            test_output="PASS",
            wall_clock_seconds=50.0,
            input_tokens=2000,
            output_tokens=800,
            tool_calls=8,
            lines_changed=20,
            files_touched=["x.py"],
            skill_generation=SkillGenerationMetrics(
                wall_clock_seconds=25.0,
                input_tokens=1500,
                output_tokens=400
            )
        ),
    ]

    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(results)

    task = eval_results.results[0]
    assert task["none"] is not None
    assert task["flat_llm"] is None
    assert task["intent_layer"] is not None

    # flat_llm delta should be empty (missing condition)
    assert task["deltas"]["flat_llm"] == {}
    # intent_layer delta should exist
    assert task["deltas"]["intent_layer"]["time_percent"] == "-44.4%"


def test_summary_three_success_rates(three_condition_results):
    """Summary has all three success rates."""
    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(three_condition_results)

    summary = eval_results.summary
    assert summary["total_tasks"] == 1
    assert summary["infrastructure_errors"] == 0
    assert summary["none_success_rate"] == 0.0
    assert summary["flat_llm_success_rate"] == 1.0
    assert summary["intent_layer_success_rate"] == 1.0


def test_markdown_multi_row_layout(tmp_path, three_condition_results):
    """Markdown output has multi-row layout with correct structure."""
    reporter = Reporter(output_dir=str(tmp_path))
    eval_results = reporter.compile_results(three_condition_results)
    md_path = reporter.write_markdown(eval_results)

    with open(md_path) as f:
        content = f.read()

    # Header has new columns
    assert "| Task | Condition | Success |" in content
    assert "| Time (s) |" in content

    # Summary has all three rates
    assert "None success rate" in content
    assert "Flat LLM success rate" in content
    assert "Intent Layer success rate" in content

    lines = content.split("\n")

    # Find data rows for fix-123
    data_rows = [l for l in lines if l.startswith("| fix-123 |")]
    assert len(data_rows) == 3, f"Expected 3 rows for fix-123, got {len(data_rows)}"

    # First row: none condition, baseline deltas show em-dash
    none_row = data_rows[0]
    assert "| none |" in none_row
    assert "| FAIL |" in none_row
    assert "\u2014" in none_row  # em-dash for baseline

    # Second row: flat_llm
    flat_row = data_rows[1]
    assert "| flat_llm |" in flat_row
    assert "| PASS |" in flat_row
    assert "-20.0%" in flat_row  # time delta

    # Third row: intent_layer
    il_row = data_rows[2]
    assert "| intent_layer |" in il_row
    assert "| PASS |" in il_row
    assert "-40.0%" in il_row  # time delta


def test_json_output(tmp_path, three_condition_results):
    """JSON output writes correctly with new structure."""
    reporter = Reporter(output_dir=str(tmp_path))
    eval_results = reporter.compile_results(three_condition_results)
    json_path = reporter.write_json(eval_results)

    assert Path(json_path).exists()
    with open(json_path) as f:
        data = json.load(f)

    assert "results" in data
    assert "summary" in data
    assert len(data["results"]) == 1

    task = data["results"][0]
    assert "none" in task
    assert "flat_llm" in task
    assert "intent_layer" in task
    assert "deltas" in task


def test_infrastructure_errors_excluded_from_success_rate():
    """Infrastructure errors should not count toward success rates."""
    results = [
        TaskResult(
            task_id="fix-good",
            condition=Condition.NONE,
            success=True,
            test_output="PASS",
            wall_clock_seconds=50.0,
            input_tokens=2000,
            output_tokens=1000,
            tool_calls=10,
            lines_changed=20,
            files_touched=["a.py"]
        ),
        TaskResult(
            task_id="fix-infra-fail",
            condition=Condition.NONE,
            success=False,
            test_output="",
            wall_clock_seconds=0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[],
            error="[infrastructure] clone failed: network timeout"
        ),
    ]

    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(results)

    summary = eval_results.summary
    assert summary["infrastructure_errors"] == 1
    # Only fix-good counts — 1 success out of 1 valid = 1.0
    assert summary["none_success_rate"] == 1.0


def test_pre_validation_and_skill_gen_errors_excluded():
    """Pre-validation and skill-generation errors are also excluded from stats."""
    results = [
        TaskResult(
            task_id="fix-ok",
            condition=Condition.NONE,
            success=True,
            test_output="PASS",
            wall_clock_seconds=50.0,
            input_tokens=2000,
            output_tokens=1000,
            tool_calls=10,
            lines_changed=20,
            files_touched=["a.py"]
        ),
        TaskResult(
            task_id="fix-preval",
            condition=Condition.NONE,
            success=False,
            test_output="",
            wall_clock_seconds=0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[],
            error="[pre-validation] test doesn't fail at pre_fix_commit"
        ),
        TaskResult(
            task_id="fix-skillgen",
            condition=Condition.INTENT_LAYER,
            success=False,
            test_output="",
            wall_clock_seconds=0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[],
            error="[skill-generation] no files created"
        ),
    ]

    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(results)

    summary = eval_results.summary
    assert summary["infrastructure_errors"] == 2
    assert summary["none_success_rate"] == 1.0
    assert summary["intent_layer_success_rate"] == 0


def test_multi_run_serialize_condition():
    """Multiple runs produce success_rate, median, and runs array."""
    reporter = Reporter(output_dir="/tmp")

    runs = [
        TaskResult(
            task_id="fix-multi",
            condition=Condition.NONE,
            success=True,
            test_output="PASS",
            wall_clock_seconds=100.0,
            input_tokens=5000,
            output_tokens=2000,
            tool_calls=20,
            lines_changed=50,
            files_touched=["a.py"]
        ),
        TaskResult(
            task_id="fix-multi",
            condition=Condition.NONE,
            success=False,
            test_output="FAIL",
            wall_clock_seconds=120.0,
            input_tokens=6000,
            output_tokens=2500,
            tool_calls=25,
            lines_changed=60,
            files_touched=["a.py", "b.py"]
        ),
        TaskResult(
            task_id="fix-multi",
            condition=Condition.NONE,
            success=True,
            test_output="PASS",
            wall_clock_seconds=90.0,
            input_tokens=4500,
            output_tokens=1800,
            tool_calls=18,
            lines_changed=45,
            files_touched=["a.py"]
        ),
    ]

    result = reporter._serialize_condition(runs)

    # Success rate: 2/3
    assert result["success_rate"] == 0.67
    assert result["success"] is True  # majority pass
    assert result["successes"] == 2
    assert result["total_valid_runs"] == 3

    # Median efficiency (sorted: 90, 100, 120 → median 100)
    assert result["median"]["wall_clock_seconds"] == 100.0
    assert result["median"]["tool_calls"] == 20

    # Individual runs preserved
    assert len(result["runs"]) == 3
    assert result["runs"][0]["success"] is True
    assert result["runs"][1]["success"] is False


def test_multi_run_delta():
    """Multiple runs compute deltas using medians and success rate."""
    reporter = Reporter(output_dir="/tmp")

    baseline = [
        TaskResult(
            task_id="fix-delta", condition=Condition.NONE, success=True,
            test_output="PASS", wall_clock_seconds=100.0,
            input_tokens=5000, output_tokens=2000, tool_calls=20,
            lines_changed=50, files_touched=["a.py"]
        ),
        TaskResult(
            task_id="fix-delta", condition=Condition.NONE, success=False,
            test_output="FAIL", wall_clock_seconds=100.0,
            input_tokens=5000, output_tokens=2000, tool_calls=20,
            lines_changed=50, files_touched=["a.py"]
        ),
    ]
    treatment = [
        TaskResult(
            task_id="fix-delta", condition=Condition.FLAT_LLM, success=True,
            test_output="PASS", wall_clock_seconds=80.0,
            input_tokens=4000, output_tokens=1500, tool_calls=15,
            lines_changed=30, files_touched=["a.py"]
        ),
        TaskResult(
            task_id="fix-delta", condition=Condition.FLAT_LLM, success=True,
            test_output="PASS", wall_clock_seconds=80.0,
            input_tokens=4000, output_tokens=1500, tool_calls=15,
            lines_changed=30, files_touched=["a.py"]
        ),
    ]

    delta = reporter._compute_delta(baseline, treatment)

    # Success rate: baseline 50%, treatment 100%, delta +50%
    assert delta["success_rate_delta"] == "+50%"
    # Time: (80 - 100) / 100 = -20%
    assert delta["time_percent"] == "-20.0%"
    # Tokens: (5500 - 7000) / 7000 = -21.4%
    assert delta["tokens_percent"] == "-21.4%"


def test_get_fix_metrics_all_formats():
    """_get_fix_metrics extracts correctly from all three data shapes."""
    # Multi-run median format
    multi = {"median": {
        "wall_clock_seconds": 50.0,
        "input_tokens": 3000, "output_tokens": 1000,
        "tool_calls": 10, "lines_changed": 25,
    }}
    m = Reporter._get_fix_metrics(multi)
    assert m["wall_clock_seconds"] == 50.0
    assert m["tokens"] == 4000
    assert m["tool_calls"] == 10
    assert m["lines_changed"] == 25

    # Single-run with skill_generation (fix_only)
    single_sg = {"fix_only": {
        "wall_clock_seconds": 80.0,
        "input_tokens": 4000, "output_tokens": 1500,
        "tool_calls": 15, "lines_changed": 30,
    }}
    s = Reporter._get_fix_metrics(single_sg)
    assert s["wall_clock_seconds"] == 80.0
    assert s["tokens"] == 5500

    # Single-run flat (no skill_generation)
    flat = {
        "wall_clock_seconds": 100.0,
        "input_tokens": 5000, "output_tokens": 2000,
        "tool_calls": 20, "lines_changed": 50,
    }
    f = Reporter._get_fix_metrics(flat)
    assert f["wall_clock_seconds"] == 100.0
    assert f["tokens"] == 7000


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
    assert "success_rate_delta" in delta
    assert "success" not in delta
    assert delta["success_rate_delta"] == "+1"
