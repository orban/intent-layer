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
        }

        if r.skill_generation:
            # Three-level structure for with_skill results
            result["fix_only"] = {
                "wall_clock_seconds": r.wall_clock_seconds,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "tool_calls": r.tool_calls,
                "lines_changed": r.lines_changed,
                "files_touched": r.files_touched,
            }
            result["skill_generation"] = {
                "wall_clock_seconds": r.skill_generation.wall_clock_seconds,
                "input_tokens": r.skill_generation.input_tokens,
                "output_tokens": r.skill_generation.output_tokens,
                "cache_hit": r.skill_generation.cache_hit,
            }
            result["total"] = {
                "wall_clock_seconds": (
                    r.wall_clock_seconds + r.skill_generation.wall_clock_seconds
                ),
                "input_tokens": (
                    r.input_tokens + r.skill_generation.input_tokens
                ),
                "output_tokens": (
                    r.output_tokens + r.skill_generation.output_tokens
                ),
            }
        else:
            # Flat structure for without_skill results
            result["wall_clock_seconds"] = r.wall_clock_seconds
            result["input_tokens"] = r.input_tokens
            result["output_tokens"] = r.output_tokens
            result["tool_calls"] = r.tool_calls
            result["lines_changed"] = r.lines_changed
            result["files_touched"] = r.files_touched

        if r.error:
            result["error"] = r.error

        return result

    def _compute_delta(self, without: TaskResult | None, with_skill: TaskResult | None) -> dict:
        """Compute delta between conditions using fix_only metrics."""
        if not without or not with_skill:
            return {}

        success_delta = int(with_skill.success) - int(without.success)

        # Use fix-only time (exclude skill_generation)
        time_pct = ((with_skill.wall_clock_seconds - without.wall_clock_seconds) / without.wall_clock_seconds * 100) if without.wall_clock_seconds else 0

        # Use fix-only tokens (exclude skill_generation)
        with_tokens = with_skill.input_tokens + with_skill.output_tokens
        without_tokens = without.input_tokens + without.output_tokens
        tokens_pct = ((with_tokens - without_tokens) / without_tokens * 100) if without_tokens else 0

        # tool_calls and lines_changed are already fix-only
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
            "| Task | Without Skill | With Skill | Δ Success | Δ Fix Time | Δ Fix Tokens | Δ Tools | Δ Lines | Δ Files | Index Time | Index Tokens | Cache |",
            "|------|--------------|------------|-----------|-----------|-------------|---------|---------|---------|------------|--------------|-------|",
        ]

        for r in results.results:
            without = r.get("without_skill", {})
            with_s = r.get("with_skill", {})
            delta = r.get("delta", {})

            # Extract index metrics from with_skill condition
            index_time = "N/A"
            index_tokens = "N/A"
            cache = "N/A"

            if with_s and "skill_generation" in with_s:
                skill_gen = with_s["skill_generation"]

                # Format index time
                index_time = f"{skill_gen['wall_clock_seconds']:.1f}s"

                # Format index tokens in thousands
                total_index_tokens = skill_gen['input_tokens'] + skill_gen['output_tokens']
                index_tokens = f"{total_index_tokens / 1000:.1f}k"

                # Format cache hit/miss
                cache_hit = skill_gen.get('cache_hit', False)
                cache = "✓" if cache_hit else "✗"

            # Calculate files delta
            files_delta = "N/A"
            if without and with_s and "fix_only" in with_s:
                without_files = len(without.get('files_touched', []))
                with_files = len(with_s['fix_only'].get('files_touched', []))
                if without_files > 0:
                    files_pct = ((with_files - without_files) / without_files * 100)
                    files_delta = f"{files_pct:+.1f}%"

            lines.append(
                f"| {r['task_id']} | "
                f"{'PASS' if without.get('success') else 'FAIL'} | "
                f"{'PASS' if with_s.get('success') else 'FAIL'} | "
                f"{delta.get('success', 'N/A')} | "
                f"{delta.get('time_percent', 'N/A')} | "
                f"{delta.get('tokens_percent', 'N/A')} | "
                f"{delta.get('tool_calls_percent', 'N/A')} | "
                f"{delta.get('lines_changed_percent', 'N/A')} | "
                f"{files_delta} | "
                f"{index_time} | "
                f"{index_tokens} | "
                f"{cache} |"
            )

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return str(path)
