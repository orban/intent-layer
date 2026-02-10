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


def test_reporter_separates_fix_and_indexing_metrics(sample_results):
    """Test that with_skill results have three-level structure: fix_only, skill_generation, total."""
    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(sample_results)

    task_result = eval_results.results[0]

    # without_skill should remain flat (no three-level structure)
    without = task_result["without_skill"]
    assert without["success"] is False
    assert without["wall_clock_seconds"] == 100.0
    assert without["input_tokens"] == 5000
    assert without["output_tokens"] == 2000
    assert "fix_only" not in without
    assert "skill_generation" not in without
    assert "total" not in without

    # with_skill should have three-level structure
    with_s = task_result["with_skill"]

    # fix_only metrics (bug fixing only, excludes indexing)
    assert "fix_only" in with_s
    assert with_s["fix_only"]["wall_clock_seconds"] == 60.0
    assert with_s["fix_only"]["input_tokens"] == 3000
    assert with_s["fix_only"]["output_tokens"] == 1000
    assert with_s["fix_only"]["tool_calls"] == 10
    assert with_s["fix_only"]["lines_changed"] == 25

    # skill_generation metrics (indexing only)
    assert "skill_generation" in with_s
    assert with_s["skill_generation"]["wall_clock_seconds"] == 30.0
    assert with_s["skill_generation"]["input_tokens"] == 2000
    assert with_s["skill_generation"]["output_tokens"] == 500

    # total metrics (sum of fix_only and skill_generation)
    assert "total" in with_s
    assert with_s["total"]["wall_clock_seconds"] == 90.0  # 60 + 30
    assert with_s["total"]["input_tokens"] == 5000  # 3000 + 2000
    assert with_s["total"]["output_tokens"] == 1500  # 1000 + 500

    # Common fields at top level
    assert with_s["success"] is True
    assert with_s["test_output"] == "PASS"


def test_reporter_delta_uses_fix_only_metrics(sample_results):
    """Test that delta calculations compare fix_only metrics, not totals."""
    reporter = Reporter(output_dir="/tmp")
    eval_results = reporter.compile_results(sample_results)

    task_result = eval_results.results[0]
    delta = task_result["delta"]

    # Delta should compare:
    # - without_skill: 100s, 7000 tokens (5000 + 2000)
    # - with_skill fix_only: 60s, 4000 tokens (3000 + 1000)
    # NOT with_skill total: 90s, 6500 tokens

    # Time delta: (60 - 100) / 100 = -40%
    assert delta["time_percent"] == "-40.0%"

    # Tokens delta: (4000 - 7000) / 7000 = -42.86%
    assert delta["tokens_percent"] == "-42.9%"

    # Tool calls delta: (10 - 20) / 20 = -50%
    assert delta["tool_calls_percent"] == "-50.0%"

    # Lines changed delta: (25 - 50) / 50 = -50%
    assert delta["lines_changed_percent"] == "-50.0%"


def test_markdown_report_includes_all_columns(tmp_path, sample_results):
    """Test that markdown report includes all columns including index time, tokens, and cache."""
    reporter = Reporter(output_dir=str(tmp_path))
    eval_results = reporter.compile_results(sample_results)

    md_path = reporter.write_markdown(eval_results)

    with open(md_path) as f:
        content = f.read()

    # Check that header row contains all expected columns
    assert "| Task |" in content
    assert "| Without Skill |" in content
    assert "| With Skill |" in content
    assert "| Δ Success |" in content
    assert "| Δ Fix Time |" in content
    assert "| Δ Fix Tokens |" in content
    assert "| Δ Tools |" in content
    assert "| Δ Lines |" in content
    assert "| Δ Files |" in content
    assert "| Index Time |" in content
    assert "| Index Tokens |" in content
    assert "| Cache |" in content

    # Check data rows contain expected values
    lines = content.split('\n')

    # Find the data row (should be after the separator row)
    data_row = None
    for i, line in enumerate(lines):
        if line.startswith('| fix-123 |'):
            data_row = line
            break

    assert data_row is not None, "Could not find data row for fix-123"

    # Data row should have:
    # - Task: fix-123
    # - Without Skill: FAIL
    # - With Skill: PASS
    # - Δ Success: +1
    # - Δ Fix Time: -40.0%
    # - Δ Fix Tokens: -42.9%
    # - Δ Tools: -50.0%
    # - Δ Lines: -50.0%
    # - Δ Files: -50.0% (2 files to 1 file)
    # - Index Time: 30.0s
    # - Index Tokens: 2.5k (2000 + 500)
    # - Cache: ✗ (cache_hit is None/False)

    assert "| fix-123 |" in data_row
    assert "| FAIL |" in data_row
    assert "| PASS |" in data_row
    assert "| +1 |" in data_row
    assert "| -40.0% |" in data_row
    assert "| -42.9% |" in data_row
    assert "| -50.0% |" in data_row  # tools
    assert "| 30.0s |" in data_row  # index time
    assert "| 2.5k |" in data_row  # index tokens (2000 + 500)
    assert "| ✗ |" in data_row  # cache miss
