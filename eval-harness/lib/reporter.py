# lib/reporter.py
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.task_runner import TaskResult, Condition


@dataclass
class EvalResults:
    eval_id: str
    timestamp: str
    results: list[dict[str, Any]]
    summary: dict[str, Any]


class Reporter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def compile_results(self, results: list[TaskResult]) -> EvalResults:
        """Compile task results into structured eval results."""
        # Group by task_id
        grouped: dict[str, dict[str, TaskResult]] = {}
        for r in results:
            if r.task_id not in grouped:
                grouped[r.task_id] = {}
            grouped[r.task_id][r.condition.value] = r

        compiled = []
        for task_id, conditions in grouped.items():
            without = conditions.get("without_skill")
            with_skill = conditions.get("with_skill")

            task_result = {
                "task_id": task_id,
                "without_skill": self._serialize_result(without) if without else None,
                "with_skill": self._serialize_result(with_skill) if with_skill else None,
                "delta": self._compute_delta(without, with_skill)
            }
            compiled.append(task_result)

        summary = self._compute_summary(results)

        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        eval_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")

        return EvalResults(
            eval_id=eval_id,
            timestamp=timestamp,
            results=compiled,
            summary=summary
        )

    def _serialize_result(self, r: TaskResult) -> dict:
        """Serialize a TaskResult to dict."""
        result = {
            "success": r.success,
            "test_output": r.test_output[:1000],  # Truncate
            "wall_clock_seconds": r.wall_clock_seconds,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "tool_calls": r.tool_calls,
            "lines_changed": r.lines_changed,
            "files_touched": r.files_touched,
        }

        if r.skill_generation:
            result["skill_generation"] = {
                "wall_clock_seconds": r.skill_generation.wall_clock_seconds,
                "input_tokens": r.skill_generation.input_tokens,
                "output_tokens": r.skill_generation.output_tokens
            }
            result["total_wall_clock_seconds"] = (
                r.wall_clock_seconds + r.skill_generation.wall_clock_seconds
            )
            result["total_input_tokens"] = (
                r.input_tokens + r.skill_generation.input_tokens
            )
            result["total_output_tokens"] = (
                r.output_tokens + r.skill_generation.output_tokens
            )

        if r.error:
            result["error"] = r.error

        return result

    def _compute_delta(self, without: TaskResult | None, with_skill: TaskResult | None) -> dict:
        """Compute delta between conditions."""
        if not without or not with_skill:
            return {}

        success_delta = int(with_skill.success) - int(without.success)

        # For with_skill, use total time including skill generation
        with_time = with_skill.wall_clock_seconds
        if with_skill.skill_generation:
            with_time += with_skill.skill_generation.wall_clock_seconds

        time_pct = ((with_time - without.wall_clock_seconds) / without.wall_clock_seconds * 100) if without.wall_clock_seconds else 0

        with_tokens = with_skill.input_tokens + with_skill.output_tokens
        if with_skill.skill_generation:
            with_tokens += with_skill.skill_generation.input_tokens + with_skill.skill_generation.output_tokens
        without_tokens = without.input_tokens + without.output_tokens

        tokens_pct = ((with_tokens - without_tokens) / without_tokens * 100) if without_tokens else 0

        tools_pct = ((with_skill.tool_calls - without.tool_calls) / without.tool_calls * 100) if without.tool_calls else 0

        lines_pct = ((with_skill.lines_changed - without.lines_changed) / without.lines_changed * 100) if without.lines_changed else 0

        return {
            "success": f"+{success_delta}" if success_delta >= 0 else str(success_delta),
            "time_percent": f"{time_pct:+.1f}%",
            "tokens_percent": f"{tokens_pct:+.1f}%",
            "tool_calls_percent": f"{tools_pct:+.1f}%",
            "lines_changed_percent": f"{lines_pct:+.1f}%"
        }

    def _compute_summary(self, results: list[TaskResult]) -> dict:
        """Compute overall summary statistics."""
        without = [r for r in results if r.condition == Condition.WITHOUT_SKILL]
        with_skill = [r for r in results if r.condition == Condition.WITH_SKILL]

        without_success = sum(1 for r in without if r.success) / len(without) if without else 0
        with_success = sum(1 for r in with_skill if r.success) / len(with_skill) if with_skill else 0

        return {
            "total_tasks": len(set(r.task_id for r in results)),
            "without_skill_success_rate": round(without_success, 2),
            "with_skill_success_rate": round(with_success, 2),
        }

    def write_json(self, results: EvalResults) -> str:
        """Write results to JSON file."""
        path = self.output_dir / f"{results.eval_id}.json"
        with open(path, "w") as f:
            json.dump(asdict(results), f, indent=2)
        return str(path)

    def write_markdown(self, results: EvalResults) -> str:
        """Write results to Markdown file."""
        path = self.output_dir / f"{results.eval_id}.md"

        lines = [
            f"# Eval Results: {results.eval_id}",
            "",
            f"**Timestamp:** {results.timestamp}",
            "",
            "## Summary",
            "",
            f"- **Total tasks:** {results.summary['total_tasks']}",
            f"- **Without skill success rate:** {results.summary['without_skill_success_rate']:.0%}",
            f"- **With skill success rate:** {results.summary['with_skill_success_rate']:.0%}",
            "",
            "## Results",
            "",
            "| Task | Without Skill | With Skill | Δ Success | Δ Time | Δ Tokens |",
            "|------|--------------|------------|-----------|--------|----------|",
        ]

        for r in results.results:
            without = r.get("without_skill", {})
            with_s = r.get("with_skill", {})
            delta = r.get("delta", {})

            lines.append(
                f"| {r['task_id']} | "
                f"{'PASS' if without.get('success') else 'FAIL'} | "
                f"{'PASS' if with_s.get('success') else 'FAIL'} | "
                f"{delta.get('success', 'N/A')} | "
                f"{delta.get('time_percent', 'N/A')} | "
                f"{delta.get('tokens_percent', 'N/A')} |"
            )

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return str(path)
