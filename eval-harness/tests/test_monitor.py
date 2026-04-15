# tests/test_monitor.py
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from lib.monitor import (
    MonitorConfig,
    MonitorState,
    read_status,
    send_command,
    count_task_infra_failures,
    evaluate_policies,
    execute_actions,
)


@pytest.fixture
def results_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _write_status(results_dir: Path, **overrides):
    """Write a .eval-status.json with sensible defaults."""
    status = {
        "eval_id": "test-eval",
        "timestamp": "2026-02-24T12:00:00",
        "uptime_seconds": 600,
        "workers": 4,
        "paused": False,
        "batch_total": 60,
        "completed": 30,
        "passes": 20,
        "genuine_failures": 5,
        "infra_failures": 5,
        "remaining": 30,
        "pass_rate": 0.8,
        "infra_rate": 0.167,
        **overrides,
    }
    path = results_dir / ".eval-status.json"
    path.write_text(json.dumps(status))
    return status


def _write_checkpoint(results_dir: Path, results: list[dict]):
    """Write a minimal checkpoint file."""
    checkpoint = {
        "eval_id": "test-eval",
        "checkpoint": True,
        "completed_runs": sum(1 for _ in results),
        "results": results,
    }
    path = results_dir / "in-progress-test-eval.json"
    path.write_text(json.dumps(checkpoint))


class TestReadStatus:
    def test_reads_valid_status(self, results_dir):
        _write_status(results_dir, completed=42)
        status = read_status(results_dir)
        assert status["completed"] == 42

    def test_returns_none_when_missing(self, results_dir):
        assert read_status(results_dir) is None

    def test_returns_none_on_corrupt_json(self, results_dir):
        (results_dir / ".eval-status.json").write_text("not json{{{")
        assert read_status(results_dir) is None


class TestSendCommand:
    def test_creates_command_file(self, results_dir):
        send_command(results_dir, "pause")
        cmd_path = results_dir / ".eval-control" / "pause"
        assert cmd_path.exists()
        assert cmd_path.read_text() == ""

    def test_creates_command_with_value(self, results_dir):
        send_command(results_dir, "skip-task", "fix-broken-task")
        cmd_path = results_dir / ".eval-control" / "skip-task"
        assert cmd_path.read_text() == "fix-broken-task"

    def test_creates_control_dir(self, results_dir):
        send_command(results_dir, "resume")
        assert (results_dir / ".eval-control").is_dir()


class TestCountTaskInfraFailures:
    def test_counts_all_infra_task(self):
        checkpoint = {"results": [{
            "task_id": "task-broken",
            "none": {"runs": [
                {"error": "[infrastructure] Docker setup timed out"},
                {"error": "[pre-validation] test failed"},
            ]},
            "flat_llm": {"runs": [
                {"error": "[infrastructure] Docker setup timed out"},
            ]},
        }]}
        counts = count_task_infra_failures(checkpoint)
        assert counts["task-broken"] == 3

    def test_ignores_mixed_task(self):
        """Task with some genuine failures is NOT counted as all-infra."""
        checkpoint = {"results": [{
            "task_id": "task-mixed",
            "none": {"runs": [
                {"error": "[infrastructure] Docker setup timed out"},
                {"success": True},  # genuine result
            ]},
        }]}
        counts = count_task_infra_failures(checkpoint)
        assert "task-mixed" not in counts

    def test_empty_results(self):
        assert count_task_infra_failures({"results": []}) == {}


class TestEvaluatePolicies:
    def _config(self, results_dir):
        return MonitorConfig(results_dir=results_dir)

    def test_detects_progress(self, results_dir):
        """Completed count advancing resets stall timer."""
        config = self._config(results_dir)
        state = MonitorState(last_completed=10)
        status = {"completed": 15, "remaining": 45, "workers": 4,
                  "infra_rate": 0.1, "paused": False}
        actions = evaluate_policies(status, state, config)

        assert state.last_completed == 15
        # No stall warning since progress was made
        assert not any(a["type"] == "log_warning" for a in actions)

    @patch("lib.monitor.check_docker", return_value=False)
    def test_stall_triggers_docker_check(self, mock_docker, results_dir):
        """No progress beyond stall_timeout triggers Docker check."""
        config = self._config(results_dir)
        config.stall_timeout = 10
        state = MonitorState(
            last_completed=10,
            last_progress_time=time.time() - 60,  # 60s ago
        )
        status = {"completed": 10, "remaining": 50, "workers": 4,
                  "infra_rate": 0.1, "paused": False}
        actions = evaluate_policies(status, state, config)

        assert any(a["type"] == "docker_restart" for a in actions)

    @patch("lib.monitor.check_docker", return_value=True)
    def test_stall_with_healthy_docker_warns(self, mock_docker, results_dir):
        """Stall with healthy Docker logs warning instead of restart."""
        config = self._config(results_dir)
        config.stall_timeout = 10
        state = MonitorState(
            last_completed=10,
            last_progress_time=time.time() - 60,
        )
        status = {"completed": 10, "remaining": 50, "workers": 4,
                  "infra_rate": 0.1, "paused": False}
        actions = evaluate_policies(status, state, config)

        assert any(a["type"] == "log_warning" for a in actions)
        assert not any(a["type"] == "docker_restart" for a in actions)

    def test_skip_task_after_infra_threshold(self, results_dir):
        """Task with all infra failures gets skipped."""
        config = self._config(results_dir)
        config.infra_skip_threshold = 2
        # Write checkpoint with all-infra task
        _write_checkpoint(results_dir, [{
            "task_id": "task-broken",
            "none": {"runs": [
                {"error": "[infrastructure] fail"},
                {"error": "[infrastructure] fail"},
            ]},
            "flat_llm": {"runs": [
                {"error": "[infrastructure] fail"},
            ]},
        }])
        state = MonitorState(last_completed=5)
        status = {"completed": 5, "remaining": 55, "workers": 4,
                  "infra_rate": 0.3, "paused": False}
        actions = evaluate_policies(status, state, config)

        skip_actions = [a for a in actions if a["type"] == "skip_task"]
        assert len(skip_actions) == 1
        assert skip_actions[0]["value"] == "task-broken"

    def test_skip_task_idempotent(self, results_dir):
        """Already-skipped task is not skipped again."""
        config = self._config(results_dir)
        config.infra_skip_threshold = 1
        _write_checkpoint(results_dir, [{
            "task_id": "task-broken",
            "none": {"runs": [{"error": "[infrastructure] fail"}]},
        }])
        state = MonitorState(
            last_completed=5,
            skipped_tasks={"task-broken"},
        )
        status = {"completed": 5, "remaining": 55, "workers": 4,
                  "infra_rate": 0.3, "paused": False}
        actions = evaluate_policies(status, state, config)
        assert not any(a["type"] == "skip_task" for a in actions)

    def test_worker_recovery(self, results_dir):
        """Low infra rate triggers worker recovery."""
        config = self._config(results_dir)
        config.max_workers_recovery = 8
        state = MonitorState(last_completed=10)
        status = {"completed": 10, "remaining": 50, "workers": 2,
                  "infra_rate": 0.05, "paused": False}
        actions = evaluate_policies(status, state, config)

        worker_actions = [a for a in actions if a["type"] == "set_workers"]
        assert len(worker_actions) == 1
        assert worker_actions[0]["value"] == "8"

    def test_no_worker_recovery_when_high_infra(self, results_dir):
        """Don't bump workers when infra rate is high."""
        config = self._config(results_dir)
        state = MonitorState(last_completed=10)
        status = {"completed": 10, "remaining": 50, "workers": 2,
                  "infra_rate": 0.4, "paused": False}
        actions = evaluate_policies(status, state, config)
        assert not any(a["type"] == "set_workers" for a in actions)

    def test_eval_complete(self, results_dir):
        """Remaining=0 triggers eval_complete."""
        config = self._config(results_dir)
        state = MonitorState(last_completed=60)
        status = {"completed": 60, "remaining": 0, "workers": 4,
                  "infra_rate": 0.1, "pass_rate": 0.75, "paused": False}
        actions = evaluate_policies(status, state, config)

        assert any(a["type"] == "eval_complete" for a in actions)

    def test_no_stall_when_paused(self, results_dir):
        """Paused eval doesn't trigger stall detection."""
        config = self._config(results_dir)
        config.stall_timeout = 10
        state = MonitorState(
            last_completed=10,
            last_progress_time=time.time() - 600,
        )
        status = {"completed": 10, "remaining": 50, "workers": 4,
                  "infra_rate": 0.1, "paused": True}
        actions = evaluate_policies(status, state, config)
        assert not any(a["type"] in ("docker_restart", "log_warning") for a in actions)


class TestExecuteActions:
    def test_skip_task_sends_command(self, results_dir):
        config = MonitorConfig(results_dir=results_dir)
        state = MonitorState()
        actions = [{
            "type": "skip_task",
            "command": "skip-task",
            "value": "task-broken",
            "reason": "test",
        }]
        execute_actions(actions, state, config)

        assert "task-broken" in state.skipped_tasks
        cmd_path = results_dir / ".eval-control" / "skip-task"
        assert cmd_path.exists()
        assert cmd_path.read_text() == "task-broken"

    def test_set_workers_sends_command(self, results_dir):
        config = MonitorConfig(results_dir=results_dir)
        state = MonitorState()
        actions = [{
            "type": "set_workers",
            "command": "set-workers",
            "value": "8",
            "reason": "test",
        }]
        execute_actions(actions, state, config)

        cmd_path = results_dir / ".eval-control" / "set-workers"
        assert cmd_path.exists()
        assert cmd_path.read_text() == "8"

    def test_actions_logged(self, results_dir):
        config = MonitorConfig(results_dir=results_dir)
        state = MonitorState()
        actions = [{"type": "log_warning", "reason": "test warning"}]
        execute_actions(actions, state, config)
        assert len(state.actions_taken) == 1
        assert state.actions_taken[0]["reason"] == "test warning"
