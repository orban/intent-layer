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
            none_result = conditions.get("none")
            flat_result = conditions.get("flat_llm")
            il_result = conditions.get("intent_layer")

            task_result = {
                "task_id": task_id,
                "none": self._serialize_result(none_result) if none_result else None,
                "flat_llm": self._serialize_result(flat_result) if flat_result else None,
                "intent_layer": self._serialize_result(il_result) if il_result else None,
                "deltas": {
                    "flat_llm": self._compute_single_delta(none_result, flat_result),
                    "intent_layer": self._compute_single_delta(none_result, il_result),
                }
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

    def _compute_single_delta(self, baseline: TaskResult | None, treatment: TaskResult | None) -> dict:
        """Compute delta between baseline and treatment using fix_only metrics."""
        if not baseline or not treatment:
            return {}

        success_delta = int(treatment.success) - int(baseline.success)

        # Use fix-only time (exclude skill_generation)
        if baseline.wall_clock_seconds:
            time_pct = (treatment.wall_clock_seconds - baseline.wall_clock_seconds) / baseline.wall_clock_seconds * 100
        else:
            time_pct = 0

        # Use fix-only tokens (exclude skill_generation)
        treatment_tokens = treatment.input_tokens + treatment.output_tokens
        baseline_tokens = baseline.input_tokens + baseline.output_tokens
        if baseline_tokens:
            tokens_pct = (treatment_tokens - baseline_tokens) / baseline_tokens * 100
        else:
            tokens_pct = 0

        # tool_calls and lines_changed are already fix-only
        if baseline.tool_calls:
            tools_pct = (treatment.tool_calls - baseline.tool_calls) / baseline.tool_calls * 100
        else:
            tools_pct = 0

        if baseline.lines_changed:
            lines_pct = (treatment.lines_changed - baseline.lines_changed) / baseline.lines_changed * 100
        else:
            lines_pct = 0

        return {
            "success": f"+{success_delta}" if success_delta >= 0 else str(success_delta),
            "time_percent": f"{time_pct:+.1f}%",
            "tokens_percent": f"{tokens_pct:+.1f}%",
            "tool_calls_percent": f"{tools_pct:+.1f}%",
            "lines_changed_percent": f"{lines_pct:+.1f}%"
        }

    def _compute_summary(self, results: list[TaskResult]) -> dict:
        """Compute overall summary statistics."""
        none_results = [r for r in results if r.condition == Condition.NONE]
        flat_results = [r for r in results if r.condition == Condition.FLAT_LLM]
        il_results = [r for r in results if r.condition == Condition.INTENT_LAYER]

        return {
            "total_tasks": len(set(r.task_id for r in results)),
            "none_success_rate": round(sum(1 for r in none_results if r.success) / len(none_results), 2) if none_results else 0,
            "flat_llm_success_rate": round(sum(1 for r in flat_results if r.success) / len(flat_results), 2) if flat_results else 0,
            "intent_layer_success_rate": round(sum(1 for r in il_results if r.success) / len(il_results), 2) if il_results else 0,
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
            f"- **None success rate:** {results.summary['none_success_rate']:.0%}",
            f"- **Flat LLM success rate:** {results.summary['flat_llm_success_rate']:.0%}",
            f"- **Intent Layer success rate:** {results.summary['intent_layer_success_rate']:.0%}",
            "",
            "## Results",
            "",
            "| Task | Condition | Success | Time (s) | Tokens | Tool Calls | Lines | \u0394 Time | \u0394 Tokens |",
            "|------|-----------|---------|----------|--------|------------|-------|--------|----------|",
        ]

        for r in results.results:
            task_id = r["task_id"]
            deltas = r.get("deltas", {})

            for cond_key in ("none", "flat_llm", "intent_layer"):
                cond_data = r.get(cond_key)
                if cond_data is None:
                    continue

                success = "PASS" if cond_data.get("success") else "FAIL"

                # Use fix_only metrics for conditions with skill_generation, flat for none
                if "fix_only" in cond_data:
                    fix = cond_data["fix_only"]
                    time_s = fix["wall_clock_seconds"]
                    tokens = fix["input_tokens"] + fix["output_tokens"]
                    tool_calls = fix["tool_calls"]
                    lines_changed = fix["lines_changed"]
                else:
                    time_s = cond_data.get("wall_clock_seconds", 0)
                    tokens = cond_data.get("input_tokens", 0) + cond_data.get("output_tokens", 0)
                    tool_calls = cond_data.get("tool_calls", 0)
                    lines_changed = cond_data.get("lines_changed", 0)

                tokens_fmt = f"{tokens / 1000:.1f}k"

                # Deltas: none is baseline, shows "—"
                if cond_key == "none":
                    d_time = "\u2014"
                    d_tokens = "\u2014"
                else:
                    delta = deltas.get(cond_key, {})
                    d_time = delta.get("time_percent", "N/A")
                    d_tokens = delta.get("tokens_percent", "N/A")

                lines.append(
                    f"| {task_id} | {cond_key} | {success} | {time_s:.1f} | "
                    f"{tokens_fmt} | {tool_calls} | {lines_changed} | "
                    f"{d_time} | {d_tokens} |"
                )

            # Blank row between tasks
            lines.append("|  |  |  |  |  |  |  |  |  |")

        # Remove trailing blank row
        if lines and lines[-1] == "|  |  |  |  |  |  |  |  |  |":
            lines.pop()

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return str(path)
