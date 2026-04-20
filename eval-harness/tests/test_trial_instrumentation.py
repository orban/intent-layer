# tests/test_trial_instrumentation.py
"""End-to-end coverage for wall-clock + cost fields added to TaskResult.

The wrapper run() stamps started_at/finished_at; cost_usd is threaded in from
ClaudeResult on paths that actually invoke Claude. These fields need to
survive serialization through reporter.write_trial so downstream tooling
can reconstruct concurrency-by-second.
"""
import json
import tempfile

from lib.reporter import Reporter
from lib.task_runner import TaskResult, Condition


def _read_trial(reporter: Reporter, result: TaskResult) -> dict:
    path = reporter.write_trial(result)
    with open(path) as f:
        return json.load(f)


def test_write_trial_preserves_instrumentation_fields():
    """Populated started_at / finished_at / cost_usd round-trip through JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = Reporter(tmpdir)
        result = TaskResult(
            task_id="instr-1",
            condition=Condition.INTENT_LAYER,
            success=True,
            test_output="ok",
            wall_clock_seconds=42.5,
            input_tokens=300,
            output_tokens=150,
            tool_calls=8,
            lines_changed=3,
            files_touched=["a.py"],
            rep=0,
            started_at="2026-04-19T12:00:00+00:00",
            finished_at="2026-04-19T12:00:42+00:00",
            cost_usd=0.1234,
        )
        data = _read_trial(reporter, result)

        assert data["started_at"] == "2026-04-19T12:00:00+00:00"
        assert data["finished_at"] == "2026-04-19T12:00:42+00:00"
        assert data["cost_usd"] == 0.1234


def test_write_trial_serializes_defaults_for_new_fields():
    """Defaulted fields serialize as null (timestamps) and 0.0 (cost)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = Reporter(tmpdir)
        result = TaskResult(
            task_id="instr-2",
            condition=Condition.NONE,
            success=False,
            test_output="",
            wall_clock_seconds=0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[],
            rep=0,
        )
        data = _read_trial(reporter, result)

        assert data["started_at"] is None
        assert data["finished_at"] is None
        assert data["cost_usd"] == 0.0


def test_write_trial_includes_docker_invocations():
    """Per-Docker timings round-trip through the trial JSON as a list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = Reporter(tmpdir)
        invocations = [
            {
                "phase": "pre_validate_test",
                "invoked_at": "2026-04-19T12:00:00+00:00",
                "first_byte_at": "2026-04-19T12:00:02+00:00",
                "finished_at": "2026-04-19T12:00:25+00:00",
                "exit_code": 1,
                "timed_out": False,
            },
            {
                "phase": "post_test",
                "invoked_at": "2026-04-19T12:01:30+00:00",
                "first_byte_at": "2026-04-19T12:01:31+00:00",
                "finished_at": "2026-04-19T12:01:50+00:00",
                "exit_code": 0,
                "timed_out": False,
            },
        ]
        result = TaskResult(
            task_id="instr-3",
            condition=Condition.NONE,
            success=True,
            test_output="ok",
            wall_clock_seconds=10.0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[],
            rep=0,
            docker_invocations=invocations,
        )
        data = _read_trial(reporter, result)

        assert data["docker_invocations"] == invocations
        assert data["docker_invocations"][0]["phase"] == "pre_validate_test"
        assert data["docker_invocations"][1]["first_byte_at"] == "2026-04-19T12:01:31+00:00"


def test_write_trial_includes_stream_events():
    """Per-stream-event arrival records round-trip through the trial JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = Reporter(tmpdir)
        events = [
            {"t": 0.05, "type": "system"},
            {"t": 1.20, "type": "assistant", "tools": ["Bash"], "out": 80, "cache_read": 12000},
            {"t": 8.40, "type": "user"},
            {"t": 12.10, "type": "result", "num_turns": 3, "cost_usd": 0.01},
        ]
        result = TaskResult(
            task_id="instr-stream-1",
            condition=Condition.NONE,
            success=True,
            test_output="ok",
            wall_clock_seconds=12.5,
            input_tokens=12000,
            output_tokens=80,
            tool_calls=1,
            lines_changed=0,
            files_touched=[],
            rep=0,
            stream_events=events,
        )
        data = _read_trial(reporter, result)

        assert data["stream_events"] == events
        assert data["stream_events"][1]["tools"] == ["Bash"]
        assert data["stream_events"][3]["num_turns"] == 3


def test_record_docker_handles_partial_result_objects():
    """_record_docker tolerates result objects without instrumentation fields.

    Test mocks for run_in_docker often return a stub result with only
    exit_code/stdout/stderr. The recorder should fill timing fields with None.
    """
    from lib.task_runner import _record_docker

    class StubResult:
        def __init__(self):
            self.exit_code = 0
            self.stdout = ""
            self.stderr = ""

    invocations: list[dict] = []
    _record_docker(invocations, "test_phase", StubResult())

    assert len(invocations) == 1
    rec = invocations[0]
    assert rec["phase"] == "test_phase"
    assert rec["invoked_at"] is None
    assert rec["first_byte_at"] is None
    assert rec["finished_at"] is None
    assert rec["exit_code"] == 0


def test_run_wrapper_stamps_boundaries(monkeypatch):
    """TaskRunner.run() sets started_at and finished_at around _run_inner."""
    from lib import task_runner as tr

    runner = tr.TaskRunner.__new__(tr.TaskRunner)

    def fake_inner(self, task, condition, model=None, rep=0):
        return TaskResult(
            task_id="t",
            condition=condition,
            success=True,
            test_output="",
            wall_clock_seconds=1.0,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            lines_changed=0,
            files_touched=[],
            rep=rep,
            cost_usd=0.05,
        )

    monkeypatch.setattr(tr.TaskRunner, "_run_inner", fake_inner)

    class DummyTask:
        id = "t"

    result = runner.run(DummyTask(), Condition.NONE)

    assert result.started_at is not None
    assert result.finished_at is not None
    assert result.started_at <= result.finished_at
    assert result.cost_usd == 0.05
