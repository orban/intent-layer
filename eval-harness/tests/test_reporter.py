# tests/test_reporter.py
import pytest
import json
from pathlib import Path
from lib.reporter import Reporter, EvalResults
from lib.task_runner import TaskResult, Condition, SkillGenerationMetrics


@pytest.fixture
def sample_results():
    return [
        TaskResult(
            task_id="fix-123",
            condition=Condition.WITHOUT_SKILL,
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
            condition=Condition.WITH_SKILL,
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


def test_reporter_generates_json(tmp_path, sample_results):
    reporter = Reporter(output_dir=str(tmp_path))
    eval_results = reporter.compile_results(sample_results)

    json_path = reporter.write_json(eval_results)

    assert Path(json_path).exists()
    with open(json_path) as f:
        data = json.load(f)
    assert "results" in data
    assert "summary" in data


def test_reporter_computes_deltas(sample_results):
    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(sample_results)

    task_result = eval_results.results[0]
    assert task_result["delta"]["success"] == "+1"
    assert "time_percent" in task_result["delta"]
