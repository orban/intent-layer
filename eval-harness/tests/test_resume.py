# tests/test_resume.py
"""Tests for --resume functionality: _load_prior_results and _merge_results."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

import click
import pytest

from lib.cli import _load_prior_results, _merge_results, _recompute_summary, _is_infra_error_dict
from lib.reporter import EvalResults


def _write_json(data: dict) -> str:
    """Write data to a temp JSON file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name


# --- Fixtures: minimal prior result structures ---

def _make_prior(tasks: list[dict]) -> dict:
    return {
        "eval_id": "2026-02-17-100000",
        "timestamp": "2026-02-17T10:00:00Z",
        "results": tasks,
        "summary": {"total_tasks": len(tasks)},
    }


def _passing_condition():
    return {"success": True, "test_output": "ok", "wall_clock_seconds": 10,
            "input_tokens": 100, "output_tokens": 50, "tool_calls": 5,
            "lines_changed": 3, "files_touched": ["a.py"], "exit_code": 0}


def _failing_condition():
    return {"success": False, "test_output": "", "wall_clock_seconds": 300,
            "input_tokens": 0, "output_tokens": 0, "tool_calls": 0,
            "lines_changed": 0, "files_touched": [],
            "error": "[timeout] Claude timed out after 300.0s",
            "exit_code": -1, "is_timeout": True}


def _infra_error_condition():
    return {"success": False, "test_output": "", "wall_clock_seconds": 0,
            "input_tokens": 0, "output_tokens": 0, "tool_calls": 0,
            "lines_changed": 0, "files_touched": [],
            "error": "[empty-run] Claude produced no output (exit_code=-1, 0.0s)",
            "exit_code": -1}


def _genuine_failure_condition():
    """A real test failure — not an infra error. Counts toward the denominator."""
    return {"success": False, "test_output": "FAILED 3 tests", "wall_clock_seconds": 45,
            "input_tokens": 500, "output_tokens": 200, "tool_calls": 12,
            "lines_changed": 8, "files_touched": ["a.py"], "exit_code": 1}


def _multi_run_passing():
    """Multi-run condition where majority passed."""
    return {
        "success_rate": 0.67, "success": True, "successes": 2,
        "total_valid_runs": 3,
        "runs": [
            {"success": True, "test_output": "ok", "wall_clock_seconds": 10,
             "input_tokens": 100, "output_tokens": 50, "tool_calls": 5,
             "lines_changed": 3, "files_touched": ["a.py"]},
            {"success": True, "test_output": "ok", "wall_clock_seconds": 12,
             "input_tokens": 110, "output_tokens": 55, "tool_calls": 6,
             "lines_changed": 3, "files_touched": ["a.py"]},
            {"success": False, "test_output": "fail", "wall_clock_seconds": 15,
             "input_tokens": 120, "output_tokens": 60, "tool_calls": 7,
             "lines_changed": 0, "files_touched": []},
        ],
        "median": {"wall_clock_seconds": 12, "input_tokens": 110,
                    "output_tokens": 55, "tool_calls": 6, "lines_changed": 3},
    }


def _multi_run_failing():
    """Multi-run condition where majority failed."""
    return {
        "success_rate": 0.33, "success": False, "successes": 1,
        "total_valid_runs": 3,
        "runs": [
            {"success": False, "test_output": "fail", "wall_clock_seconds": 300,
             "input_tokens": 0, "output_tokens": 0, "tool_calls": 0,
             "lines_changed": 0, "files_touched": [],
             "error": "[timeout] Claude timed out after 300.0s"},
            {"success": True, "test_output": "ok", "wall_clock_seconds": 10,
             "input_tokens": 100, "output_tokens": 50, "tool_calls": 5,
             "lines_changed": 3, "files_touched": ["a.py"]},
            {"success": False, "test_output": "fail", "wall_clock_seconds": 300,
             "input_tokens": 0, "output_tokens": 0, "tool_calls": 0,
             "lines_changed": 0, "files_touched": [],
             "error": "[timeout] Claude timed out after 300.0s"},
        ],
        "median": {"wall_clock_seconds": 300, "input_tokens": 0,
                    "output_tokens": 0, "tool_calls": 0, "lines_changed": 0},
    }


# --- _load_prior_results tests ---

class TestLoadPriorResults:
    def test_identifies_passed_pairs(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _failing_condition(),
            "intent_layer": _passing_condition(),
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, data = _load_prior_results(path)

        assert ("task-1", "none") in passed
        assert ("task-1", "flat_llm") not in passed
        assert ("task-1", "intent_layer") in passed
        assert len(passed) == 2

    def test_excludes_infra_errors(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _infra_error_condition(),
            "flat_llm": _infra_error_condition(),
            "intent_layer": _infra_error_condition(),
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert len(passed) == 0

    def test_validates_structure(self):
        path = _write_json({"bad": "data"})
        with pytest.raises(click.ClickException, match="missing 'results' key"):
            _load_prior_results(path)

    def test_rejects_non_dict_json(self):
        path = _write_json([1, 2, 3])
        with pytest.raises(click.ClickException, match="missing 'results' key"):
            _load_prior_results(path)

    def test_rejects_non_list_results(self):
        path = _write_json({"results": "not a list"})
        with pytest.raises(click.ClickException, match="'results' must be a list"):
            _load_prior_results(path)

    def test_rejects_invalid_json(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write("{not valid json")
        f.close()
        with pytest.raises(click.ClickException, match="Invalid JSON"):
            _load_prior_results(f.name)

    def test_rejects_task_missing_task_id(self):
        prior = {"results": [{"none": _passing_condition()}]}
        path = _write_json(prior)
        with pytest.raises(click.ClickException, match="task at index 0 missing 'task_id'"):
            _load_prior_results(path)

    def test_handles_null_conditions(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": None,
            "intent_layer": None,
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert passed == {("task-1", "none")}

    def test_multi_run_passing_is_carried_forward(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _multi_run_passing(),
            "flat_llm": _multi_run_failing(),
            "intent_layer": _multi_run_passing(),
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert ("task-1", "none") in passed
        assert ("task-1", "flat_llm") not in passed
        assert ("task-1", "intent_layer") in passed

    def test_multi_run_failing_not_carried_forward(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _multi_run_failing(),
            "flat_llm": _multi_run_failing(),
            "intent_layer": _multi_run_failing(),
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert len(passed) == 0

    def test_mixed_single_and_multi_run(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),  # single-run pass
            "flat_llm": _multi_run_failing(),  # multi-run fail
            "intent_layer": _multi_run_passing(),  # multi-run pass
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert ("task-1", "none") in passed
        assert ("task-1", "flat_llm") not in passed
        assert ("task-1", "intent_layer") in passed

    def test_multiple_tasks(self):
        prior = _make_prior([
            {"task_id": "task-1",
             "none": _passing_condition(),
             "flat_llm": _passing_condition(),
             "intent_layer": _passing_condition(),
             "deltas": {}},
            {"task_id": "task-2",
             "none": _failing_condition(),
             "flat_llm": _failing_condition(),
             "intent_layer": _failing_condition(),
             "deltas": {}},
        ])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert len(passed) == 3  # all 3 conditions of task-1
        assert all(tid == "task-1" for tid, _ in passed)


# --- _recompute_summary tests ---

class TestRecomputeSummary:
    def test_single_run_summary(self):
        results = [{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _failing_condition(),
            "intent_layer": _passing_condition(),
        }]
        summary = _recompute_summary(results)

        assert summary["total_tasks"] == 1
        assert summary["none_success_rate"] == 1.0
        assert summary["flat_llm_success_rate"] == 0  # timeout is infra error
        assert summary["intent_layer_success_rate"] == 1.0

    def test_multi_run_summary(self):
        results = [{
            "task_id": "task-1",
            "none": _multi_run_passing(),
            "flat_llm": _multi_run_failing(),
            "intent_layer": _multi_run_passing(),
        }]
        summary = _recompute_summary(results)

        assert summary["total_tasks"] == 1
        assert summary["none_success_rate"] == 0.67
        assert summary["intent_layer_success_rate"] == 0.67
        # flat_llm: 1 success out of 3 valid = 0.33
        assert summary["flat_llm_success_rate"] == 0.33

    def test_infra_errors_counted(self):
        results = [{
            "task_id": "task-1",
            "none": _infra_error_condition(),
            "flat_llm": None,
            "intent_layer": None,
        }]
        summary = _recompute_summary(results)

        assert summary["infrastructure_errors"] == 1

    def test_single_run_no_cis(self):
        """Single-run data should not produce CI fields."""
        results = [{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _passing_condition(),
            "intent_layer": _passing_condition(),
        }]
        summary = _recompute_summary(results)

        assert "none_ci_90" not in summary
        assert "flat_llm_vs_none_significant" not in summary

    def test_multi_run_produces_cis(self):
        """Multi-run data should produce Wilson Score CIs."""
        results = [{
            "task_id": "task-1",
            "none": _multi_run_passing(),
            "flat_llm": _multi_run_failing(),
            "intent_layer": _multi_run_passing(),
        }]
        summary = _recompute_summary(results)

        # CIs should be present for all conditions with data
        assert "none_ci_90" in summary
        assert "flat_llm_ci_90" in summary
        assert "intent_layer_ci_90" in summary

        # CI structure
        none_ci = summary["none_ci_90"]
        assert "lower" in none_ci
        assert "upper" in none_ci
        assert 0 <= none_ci["lower"] <= none_ci["upper"] <= 1

        # Significance flags should exist
        assert "flat_llm_vs_none_significant" in summary
        assert "intent_layer_vs_none_significant" in summary


# --- _merge_results tests ---

class TestMergeResults:
    def test_carried_forward_conditions_preserved(self):
        """Passed conditions from prior data should appear in merged output."""
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _failing_condition(),
            "intent_layer": _passing_condition(),
            "deltas": {"flat_llm": {}, "intent_layer": {"time_percent": "+5%"}},
        }])

        passed = {("task-1", "none"), ("task-1", "intent_layer")}

        # New results only have the re-run condition (flat_llm)
        new_flat = {"success": True, "test_output": "fixed", "wall_clock_seconds": 50,
                    "input_tokens": 200, "output_tokens": 100, "tool_calls": 10,
                    "lines_changed": 5, "files_touched": ["b.py"], "exit_code": 0}
        new_eval = EvalResults(
            eval_id="2026-02-17-120000",
            timestamp="2026-02-17T12:00:00Z",
            results=[{
                "task_id": "task-1",
                "none": None, "flat_llm": new_flat, "intent_layer": None,
                "deltas": {"flat_llm": {}, "intent_layer": {}},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)

        assert len(merged.results) == 1
        task = merged.results[0]
        # none and intent_layer carried from prior
        assert task["none"]["success"] is True
        assert task["none"]["wall_clock_seconds"] == 10
        assert task["intent_layer"]["success"] is True
        # flat_llm replaced with new
        assert task["flat_llm"]["success"] is True
        assert task["flat_llm"]["wall_clock_seconds"] == 50

    def test_mixed_task_deltas_cleared(self):
        """Tasks with both old and new conditions get deltas note."""
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _failing_condition(),
            "intent_layer": _passing_condition(),
            "deltas": {},
        }])
        passed = {("task-1", "none"), ("task-1", "intent_layer")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-1",
                "none": None, "flat_llm": _passing_condition(), "intent_layer": None,
                "deltas": {},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        assert "note" in merged.results[0]["deltas"]

    def test_fully_rerun_task_uses_new_deltas(self):
        """If all conditions were re-run, use new deltas."""
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _failing_condition(),
            "flat_llm": _failing_condition(),
            "intent_layer": _failing_condition(),
            "deltas": {},
        }])
        passed = set()  # nothing passed
        new_deltas = {"flat_llm": {"time_percent": "+10%"}, "intent_layer": {}}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-1",
                "none": _passing_condition(),
                "flat_llm": _passing_condition(),
                "intent_layer": _passing_condition(),
                "deltas": new_deltas,
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        assert merged.results[0]["deltas"] == new_deltas

    def test_preserves_task_order_from_prior(self):
        prior = _make_prior([
            {"task_id": "task-a", "none": _passing_condition(),
             "flat_llm": None, "intent_layer": None, "deltas": {}},
            {"task_id": "task-b", "none": _failing_condition(),
             "flat_llm": None, "intent_layer": None, "deltas": {}},
        ])
        passed = {("task-a", "none")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-b",
                "none": _passing_condition(),
                "flat_llm": None, "intent_layer": None,
                "deltas": {},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        assert [r["task_id"] for r in merged.results] == ["task-a", "task-b"]

    def test_summary_recomputed(self):
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _failing_condition(),
            "intent_layer": _passing_condition(),
            "deltas": {},
        }])
        passed = {("task-1", "none"), ("task-1", "intent_layer")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-1",
                "none": None, "flat_llm": _passing_condition(), "intent_layer": None,
                "deltas": {},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        assert merged.summary["total_tasks"] == 1
        assert merged.summary["none_success_rate"] == 1.0
        assert merged.summary["flat_llm_success_rate"] == 1.0
        assert merged.summary["intent_layer_success_rate"] == 1.0

    def test_multi_run_carried_forward(self):
        """Multi-run passing conditions are carried forward intact."""
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _multi_run_passing(),
            "flat_llm": _multi_run_failing(),
            "intent_layer": _multi_run_passing(),
            "deltas": {},
        }])
        passed = {("task-1", "none"), ("task-1", "intent_layer")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-1",
                "none": None, "flat_llm": _multi_run_passing(), "intent_layer": None,
                "deltas": {},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        task = merged.results[0]
        # Multi-run structure preserved
        assert "runs" in task["none"]
        assert len(task["none"]["runs"]) == 3
        assert "runs" in task["flat_llm"]

    def test_prior_task_dropped_when_not_passed_and_not_rerun(self):
        """A prior task with no passed pairs and not re-run gets dropped."""
        prior = _make_prior([
            {"task_id": "task-1", "none": _passing_condition(),
             "flat_llm": None, "intent_layer": None, "deltas": {}},
            {"task_id": "task-removed", "none": _failing_condition(),
             "flat_llm": None, "intent_layer": None, "deltas": {}},
        ])
        passed = {("task-1", "none")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[],  # task-removed not re-run
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        assert [r["task_id"] for r in merged.results] == ["task-1"]

    def test_new_only_task_appended(self):
        """A task only in new results (not in prior) is appended."""
        prior = _make_prior([
            {"task_id": "task-1", "none": _passing_condition(),
             "flat_llm": None, "intent_layer": None, "deltas": {}},
        ])
        passed = {("task-1", "none")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-new",
                "none": _passing_condition(),
                "flat_llm": None, "intent_layer": None,
                "deltas": {},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        assert [r["task_id"] for r in merged.results] == ["task-1", "task-new"]

    def test_non_rerun_failed_condition_preserved_from_prior(self):
        """A failed condition that wasn't re-run keeps its prior value."""
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _passing_condition(),
            "flat_llm": _genuine_failure_condition(),  # failed but not infra
            "intent_layer": _genuine_failure_condition(),
            "deltas": {},
        }])
        # Only none passed; re-run only intent_layer via --condition
        passed = {("task-1", "none")}
        new_eval = EvalResults(
            eval_id="new", timestamp="now",
            results=[{
                "task_id": "task-1",
                "none": None, "flat_llm": None,
                "intent_layer": _passing_condition(),
                "deltas": {},
            }],
            summary={},
        )

        merged = _merge_results(new_eval, prior, passed)
        task = merged.results[0]
        # flat_llm not in passed, not in new — preserved from prior
        assert task["flat_llm"]["success"] is False
        assert task["flat_llm"]["wall_clock_seconds"] == 45


# --- _is_infra_error_dict tests ---

class TestIsInfraErrorDict:
    def test_all_infra_prefixes(self):
        for prefix in ("[infrastructure]", "[pre-validation]",
                       "[skill-generation]", "[empty-run]", "[timeout]"):
            cond = {"error": f"{prefix} something went wrong"}
            assert _is_infra_error_dict(cond) is True

    def test_genuine_failure_not_infra(self):
        assert _is_infra_error_dict(_genuine_failure_condition()) is False

    def test_no_error_field(self):
        assert _is_infra_error_dict(_passing_condition()) is False

    def test_non_prefixed_error(self):
        cond = {"error": "tests failed with exit code 1"}
        assert _is_infra_error_dict(cond) is False


# --- _recompute_summary with genuine failures ---

class TestRecomputeSummaryGenuineFailures:
    def test_genuine_failure_counted_in_denominator(self):
        """A real test failure counts toward the denominator, unlike infra errors."""
        results = [{
            "task_id": "task-1",
            "none": _genuine_failure_condition(),
            "flat_llm": _infra_error_condition(),
            "intent_layer": _passing_condition(),
        }]
        summary = _recompute_summary(results)

        # none: 0 successes / 1 valid (genuine failure counted)
        assert summary["none_success_rate"] == 0.0
        # flat_llm: infra error, excluded from denominator
        assert summary["flat_llm_success_rate"] == 0
        # intent_layer: 1/1
        assert summary["intent_layer_success_rate"] == 1.0
        assert summary["infrastructure_errors"] == 1

    def test_empty_results(self):
        summary = _recompute_summary([])

        assert summary["total_tasks"] == 0
        assert summary["none_success_rate"] == 0
        assert summary["flat_llm_success_rate"] == 0
        assert summary["intent_layer_success_rate"] == 0
        assert summary["infrastructure_errors"] == 0


# --- _load_prior_results with genuine failures ---

class TestLoadGenuineFailures:
    def test_genuine_failure_not_carried_forward(self):
        """A real test failure (success=False, no infra error) is not passed."""
        prior = _make_prior([{
            "task_id": "task-1",
            "none": _genuine_failure_condition(),
            "flat_llm": _passing_condition(),
            "intent_layer": _genuine_failure_condition(),
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert ("task-1", "none") not in passed
        assert ("task-1", "flat_llm") in passed
        assert ("task-1", "intent_layer") not in passed

    def test_success_with_error_field_not_carried(self):
        """A condition with success=True but an error field is suspicious — not carried."""
        sus = {"success": True, "error": "something weird happened",
               "test_output": "ok", "wall_clock_seconds": 10,
               "input_tokens": 100, "output_tokens": 50, "tool_calls": 5,
               "lines_changed": 3, "files_touched": ["a.py"]}
        prior = _make_prior([{
            "task_id": "task-1",
            "none": sus,
            "flat_llm": _passing_condition(),
            "intent_layer": None,
            "deltas": {},
        }])
        path = _write_json(prior)
        passed, _ = _load_prior_results(path)

        assert ("task-1", "none") not in passed
        assert ("task-1", "flat_llm") in passed
