# lib/reporter.py
from __future__ import annotations
import json
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.task_runner import TaskResult, Condition
from lib.stats import wilson_score_interval, ci_overlap, mcnemar_test


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
        """Compile task results into structured eval results.

        When repetitions > 1, groups multiple runs of the same task+condition
        and reports medians for efficiency metrics alongside success rates.
        Individual runs are preserved in a "runs" array.
        """
        # Group by (task_id, condition) — allows multiple runs per pair
        grouped: dict[str, dict[str, list[TaskResult]]] = {}
        for r in results:
            if r.task_id not in grouped:
                grouped[r.task_id] = {}
            cond = r.condition.value
            if cond not in grouped[r.task_id]:
                grouped[r.task_id][cond] = []
            grouped[r.task_id][cond].append(r)

        compiled = []
        for task_id, conditions in grouped.items():
            none_runs = conditions.get("none", [])
            flat_runs = conditions.get("flat_llm", [])
            il_runs = conditions.get("intent_layer", [])

            task_result = {
                "task_id": task_id,
                "none": self._serialize_condition(none_runs) if none_runs else None,
                "flat_llm": self._serialize_condition(flat_runs) if flat_runs else None,
                "intent_layer": self._serialize_condition(il_runs) if il_runs else None,
                "deltas": {
                    "flat_llm": self._compute_delta(none_runs, flat_runs),
                    "intent_layer": self._compute_delta(none_runs, il_runs),
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

    def _serialize_single_result(self, r: TaskResult) -> dict:
        """Serialize a single TaskResult to dict."""
        result = {
            "success": r.success,
            "test_output": r.test_output[:1000],  # Truncate
        }

        if r.skill_generation:
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
            result["wall_clock_seconds"] = r.wall_clock_seconds
            result["input_tokens"] = r.input_tokens
            result["output_tokens"] = r.output_tokens
            result["tool_calls"] = r.tool_calls
            result["lines_changed"] = r.lines_changed
            result["files_touched"] = r.files_touched

        if r.error:
            result["error"] = r.error

        if r.exit_code is not None:
            result["exit_code"] = r.exit_code
        if r.is_timeout:
            result["is_timeout"] = r.is_timeout

        return result

    def _serialize_condition(self, runs: list[TaskResult]) -> dict:
        """Serialize one or more runs for a single condition.

        Single run: backward-compatible flat structure.
        Multiple runs: adds "runs" array + "median" summary with separated
        success rate and efficiency metrics.
        """
        valid_runs = [r for r in runs if not self._is_infra_error(r)]

        if len(runs) == 1:
            # Single run: backward-compatible
            return self._serialize_single_result(runs[0])

        # Multiple runs: include individual results + aggregated medians
        result: dict[str, Any] = {}

        # Success rate (primary metric — separated from efficiency)
        successes = sum(1 for r in valid_runs if r.success)
        result["success_rate"] = round(successes / len(valid_runs), 2) if valid_runs else 0
        result["success"] = result["success_rate"] >= 0.5  # majority pass
        result["successes"] = successes
        result["total_valid_runs"] = len(valid_runs)

        # Wilson Score confidence interval (90%)
        ci_lower, ci_upper, ci_center = wilson_score_interval(
            successes, len(valid_runs), confidence=0.90
        )
        result["ci_90"] = {"lower": round(ci_lower, 3), "upper": round(ci_upper, 3)}

        # Efficiency medians (secondary metrics — from valid runs only)
        if valid_runs:
            result["median"] = {
                "wall_clock_seconds": round(statistics.median(r.wall_clock_seconds for r in valid_runs), 1),
                "input_tokens": int(statistics.median(r.input_tokens for r in valid_runs)),
                "output_tokens": int(statistics.median(r.output_tokens for r in valid_runs)),
                "tool_calls": int(statistics.median(r.tool_calls for r in valid_runs)),
                "lines_changed": int(statistics.median(r.lines_changed for r in valid_runs)),
            }

        # Individual runs for drill-down
        result["runs"] = [self._serialize_single_result(r) for r in runs]

        return result

    @staticmethod
    def _get_fix_metrics(cond_data: dict) -> dict:
        """Extract fix-only metrics from a condition result (single or multi-run).

        Works with both single-run format and multi-run median format.
        Returns dict with wall_clock_seconds, input_tokens, output_tokens,
        tool_calls, lines_changed.
        """
        # Multi-run: use median
        if "median" in cond_data:
            m = cond_data["median"]
            return {
                "wall_clock_seconds": m["wall_clock_seconds"],
                "tokens": m["input_tokens"] + m["output_tokens"],
                "tool_calls": m["tool_calls"],
                "lines_changed": m["lines_changed"],
            }
        # Single run with skill_generation
        if "fix_only" in cond_data:
            fix = cond_data["fix_only"]
            return {
                "wall_clock_seconds": fix["wall_clock_seconds"],
                "tokens": fix["input_tokens"] + fix["output_tokens"],
                "tool_calls": fix["tool_calls"],
                "lines_changed": fix["lines_changed"],
            }
        # Single run without skill_generation
        return {
            "wall_clock_seconds": cond_data.get("wall_clock_seconds", 0),
            "tokens": cond_data.get("input_tokens", 0) + cond_data.get("output_tokens", 0),
            "tool_calls": cond_data.get("tool_calls", 0),
            "lines_changed": cond_data.get("lines_changed", 0),
        }

    def _compute_delta(self, baseline_runs: list[TaskResult], treatment_runs: list[TaskResult]) -> dict:
        """Compute delta between baseline and treatment using median metrics.

        For single runs, behaves identically to the old _compute_single_delta.
        For multiple runs, uses medians for efficiency and success rate delta.
        """
        if not baseline_runs or not treatment_runs:
            return {}

        # Filter out infra errors for stats
        b_valid = [r for r in baseline_runs if not self._is_infra_error(r)]
        t_valid = [r for r in treatment_runs if not self._is_infra_error(r)]

        if not b_valid or not t_valid:
            return {}

        # Success rate delta
        b_rate = sum(1 for r in b_valid if r.success) / len(b_valid)
        t_rate = sum(1 for r in t_valid if r.success) / len(t_valid)
        rate_delta = t_rate - b_rate

        # Median efficiency metrics
        b_time = statistics.median(r.wall_clock_seconds for r in b_valid)
        t_time = statistics.median(r.wall_clock_seconds for r in t_valid)
        b_tokens = statistics.median(r.input_tokens + r.output_tokens for r in b_valid)
        t_tokens = statistics.median(r.input_tokens + r.output_tokens for r in t_valid)
        b_tools = statistics.median(r.tool_calls for r in b_valid)
        t_tools = statistics.median(r.tool_calls for r in t_valid)
        b_lines = statistics.median(r.lines_changed for r in b_valid)
        t_lines = statistics.median(r.lines_changed for r in t_valid)

        def pct(baseline_val, treatment_val):
            if baseline_val:
                return (treatment_val - baseline_val) / baseline_val * 100
            return 0

        return {
            "success_rate_delta": f"{rate_delta:+.0%}" if len(b_valid) > 1 else (
                f"+{int(t_rate - b_rate)}" if rate_delta >= 0 else str(int(t_rate - b_rate))
            ),
            "time_percent": f"{pct(b_time, t_time):+.1f}%",
            "tokens_percent": f"{pct(b_tokens, t_tokens):+.1f}%",
            "tool_calls_percent": f"{pct(b_tools, t_tools):+.1f}%",
            "lines_changed_percent": f"{pct(b_lines, t_lines):+.1f}%"
        }

    # Error prefixes indicating harness/infrastructure failures, not experimental outcomes.
    # Used by both Reporter._is_infra_error and cli._is_infra_error_dict.
    INFRA_ERROR_PREFIXES = (
        "[infrastructure]", "[pre-validation]", "[skill-generation]",
        "[empty-run]", "[worker-crash]",
    )

    @staticmethod
    def _is_infra_error(r: TaskResult) -> bool:
        """Check if result is a non-experimental error (excluded from stats).

        Infrastructure errors, pre-validation failures, skill generation
        failures, and worker crashes all indicate harness problems, not
        experimental outcomes.
        """
        if r.error is None:
            return False
        return r.error.startswith(Reporter.INFRA_ERROR_PREFIXES)

    def _compute_summary(self, results: list[TaskResult]) -> dict:
        """Compute overall summary statistics.

        Two scoring modes:
        - Per-protocol: infra errors excluded from denominator (existing behavior)
        - ITT (intent-to-treat): all assigned tasks count, timeout/infra = fail
        """
        def success_rate(task_results: list[TaskResult]) -> float:
            """Per-protocol: exclude infra errors from denominator."""
            valid = [r for r in task_results if not self._is_infra_error(r)]
            if not valid:
                return 0
            return round(sum(1 for r in valid if r.success) / len(valid), 2)

        def itt_rate(task_results: list[TaskResult]) -> float:
            """Intent-to-treat: all tasks count, non-success = fail."""
            if not task_results:
                return 0
            return round(sum(1 for r in task_results if r.success) / len(task_results), 2)

        none_results = [r for r in results if r.condition == Condition.NONE]
        flat_results = [r for r in results if r.condition == Condition.FLAT_LLM]
        il_results = [r for r in results if r.condition == Condition.INTENT_LAYER]

        infra_errors = sum(1 for r in results if self._is_infra_error(r))

        def median_tokens(task_results: list[TaskResult]) -> int:
            """Median total tokens (input+output) for valid runs."""
            valid = [r for r in task_results if not self._is_infra_error(r)]
            if not valid:
                return 0
            return int(statistics.median(r.input_tokens + r.output_tokens for r in valid))

        summary: dict[str, Any] = {
            "total_tasks": len(set(r.task_id for r in results)),
            "infrastructure_errors": infra_errors,
            "none_success_rate": success_rate(none_results),
            "flat_llm_success_rate": success_rate(flat_results),
            "intent_layer_success_rate": success_rate(il_results),
            "none_itt_rate": itt_rate(none_results),
            "flat_llm_itt_rate": itt_rate(flat_results),
            "intent_layer_itt_rate": itt_rate(il_results),
            "none_median_tokens": median_tokens(none_results),
            "flat_llm_median_tokens": median_tokens(flat_results),
            "intent_layer_median_tokens": median_tokens(il_results),
        }

        # Add CIs when we have multi-run data
        has_multi_run = any(
            sum(1 for r2 in results if r2.task_id == r.task_id and r2.condition == r.condition) > 1
            for r in results
        )
        if has_multi_run:
            for label, cond_results in [
                ("none", none_results),
                ("flat_llm", flat_results),
                ("intent_layer", il_results),
            ]:
                valid = [r for r in cond_results if not self._is_infra_error(r)]
                if valid:
                    successes = sum(1 for r in valid if r.success)
                    ci_lower, ci_upper, _ = wilson_score_interval(successes, len(valid), 0.90)
                    summary[f"{label}_ci_90"] = {
                        "lower": round(ci_lower, 3),
                        "upper": round(ci_upper, 3),
                    }

            # Significance: check CI overlap between none and each treatment
            none_ci = summary.get("none_ci_90")
            if none_ci:
                for treatment in ("flat_llm", "intent_layer"):
                    t_ci = summary.get(f"{treatment}_ci_90")
                    if t_ci:
                        overlaps = ci_overlap(
                            (none_ci["lower"], none_ci["upper"]),
                            (t_ci["lower"], t_ci["upper"]),
                        )
                        summary[f"{treatment}_vs_none_significant"] = not overlaps

        # McNemar's paired analysis: compare conditions per (task, rep) pair
        summary["mcnemar"] = self._compute_mcnemar(results)

        return summary

    def _compute_mcnemar(self, results: list[TaskResult]) -> dict:
        """Compute McNemar's test for each pair of conditions.

        Pairs results by (task_id, rep_index) where rep_index is derived
        from ordering within each (task_id, condition) group. Excludes
        pairs where either result is an infra error.
        """
        # Group by (task_id, condition) preserving insertion order as rep index
        grouped: dict[str, dict[str, list[TaskResult]]] = {}
        for r in results:
            if r.task_id not in grouped:
                grouped[r.task_id] = {}
            cond = r.condition.value
            if cond not in grouped[r.task_id]:
                grouped[r.task_id][cond] = []
            grouped[r.task_id][cond].append(r)

        comparisons = [
            ("flat_llm", "none"),
            ("intent_layer", "none"),
            ("intent_layer", "flat_llm"),
        ]

        mcnemar_results = {}
        for cond_a, cond_b in comparisons:
            b = 0  # a passes, b fails
            c = 0  # a fails, b passes
            for task_id, conditions in grouped.items():
                a_runs = conditions.get(cond_a, [])
                b_runs = conditions.get(cond_b, [])
                # Pair by rep index (position in list)
                for rep_idx in range(min(len(a_runs), len(b_runs))):
                    ra = a_runs[rep_idx]
                    rb = b_runs[rep_idx]
                    # Exclude pairs where either is an infra error
                    if self._is_infra_error(ra) or self._is_infra_error(rb):
                        continue
                    if ra.success and not rb.success:
                        b += 1
                    elif not ra.success and rb.success:
                        c += 1
            mcnemar_results[f"{cond_a}_vs_{cond_b}"] = mcnemar_test(b, c)

        return mcnemar_results

    def write_json(self, results: EvalResults) -> str:
        """Write results to JSON file."""
        path = self.output_dir / f"{results.eval_id}.json"
        with open(path, "w") as f:
            json.dump(asdict(results), f, indent=2)
        return str(path)

    @staticmethod
    def _format_ci(ci: dict) -> str:
        """Format a CI dict as '[lower,upper]' with percentage values."""
        return f"[{ci['lower']:.0%},{ci['upper']:.0%}]"

    def write_markdown(self, results: EvalResults) -> str:
        """Write results to Markdown file.

        Handles both single-run (backward-compatible) and multi-run formats.
        Uses _get_fix_metrics() to extract efficiency numbers from any format.
        When multi-run data includes CIs, they're shown inline with pass rates.
        """
        path = self.output_dir / f"{results.eval_id}.md"
        summary = results.summary
        has_cis = "none_ci_90" in summary or "intent_layer_ci_90" in summary

        lines = [
            f"# Eval Results: {results.eval_id}",
            "",
            f"**Timestamp:** {results.timestamp}",
            "",
            "## Summary",
            "",
            f"- **Total tasks:** {summary['total_tasks']}",
            f"- **Infrastructure errors:** {summary['infrastructure_errors']}",
        ]

        # Per-condition summary with optional CIs
        for label, display_name in [
            ("none", "None"),
            ("flat_llm", "Flat LLM"),
            ("intent_layer", "Intent Layer"),
        ]:
            rate = summary[f"{label}_success_rate"]
            ci = summary.get(f"{label}_ci_90")
            if ci:
                lines.append(
                    f"- **{display_name} success rate:** {rate:.0%} "
                    f"90% CI {self._format_ci(ci)}"
                )
            else:
                lines.append(f"- **{display_name} success rate:** {rate:.0%}")

        # Per-condition median token usage
        none_tok = summary.get("none_median_tokens", 0)
        if none_tok:
            lines.append("")
            lines.append("**Median tokens (input+output, fix phase only):**")
            for label, display_name in [
                ("none", "None"),
                ("flat_llm", "Flat LLM"),
                ("intent_layer", "Intent Layer"),
            ]:
                tok = summary.get(f"{label}_median_tokens", 0)
                tok_fmt = f"{tok / 1000:.0f}k" if tok else "N/A"
                if label == "none" or not none_tok:
                    lines.append(f"- **{display_name}:** {tok_fmt}")
                else:
                    pct_diff = (tok - none_tok) / none_tok * 100
                    lines.append(f"- **{display_name}:** {tok_fmt} ({pct_diff:+.0f}% vs none)")

        # Significance flags
        if has_cis:
            lines.append("")
            for treatment, display_name in [
                ("flat_llm", "Flat LLM"),
                ("intent_layer", "Intent Layer"),
            ]:
                sig_key = f"{treatment}_vs_none_significant"
                if sig_key in summary:
                    if summary[sig_key]:
                        lines.append(f"- **{display_name} vs None:** significant (non-overlapping CIs)")
                    else:
                        lines.append(f"- **{display_name} vs None:** not significant (overlapping CIs)")

            # CI width as variance proxy
            widths = []
            for label in ("none", "flat_llm", "intent_layer"):
                ci = summary.get(f"{label}_ci_90")
                if ci:
                    widths.append((label, ci["upper"] - ci["lower"]))
            if widths:
                lines.append("")
                lines.append("**CI widths (variance proxy):** " + ", ".join(
                    f"{label}: {w:.0%}" for label, w in widths
                ))

        lines += [
            "",
            "## Results",
            "",
        ]

        # Table header — add IL vs none column when multi-run CIs exist
        if has_cis:
            lines.append(
                "| Task | Condition | Success | Time (s) | Tokens | Tool Calls | Lines "
                "| \u0394 Time | \u0394 Tokens | IL vs none |"
            )
            lines.append(
                "|------|-----------|---------|----------|--------|------------|-------"
                "|--------|----------|------------|"
            )
        else:
            lines.append(
                "| Task | Condition | Success | Time (s) | Tokens | Tool Calls | Lines "
                "| \u0394 Time | \u0394 Tokens |"
            )
            lines.append(
                "|------|-----------|---------|----------|--------|------------|-------"
                "|--------|----------|"
            )

        for r in results.results:
            task_id = r["task_id"]
            deltas = r.get("deltas", {})

            # Pre-compute per-task CI comparison for IL vs none
            none_data = r.get("none")
            il_data = r.get("intent_layer")
            il_vs_none = ""
            if has_cis and none_data and il_data:
                none_ci = none_data.get("ci_90")
                il_ci = il_data.get("ci_90")
                if none_ci and il_ci:
                    none_rate = none_data.get("success_rate", 0)
                    il_rate = il_data.get("success_rate", 0)
                    diff = il_rate - none_rate
                    overlaps = ci_overlap(
                        (none_ci["lower"], none_ci["upper"]),
                        (il_ci["lower"], il_ci["upper"]),
                    )
                    sig_label = "overlap" if overlaps else "sig."
                    il_vs_none = f"{diff:+.0%} ({sig_label})"

            for cond_key in ("none", "flat_llm", "intent_layer"):
                cond_data = r.get(cond_key)
                if cond_data is None:
                    continue

                # Success: multi-run shows rate + CI, single-run shows PASS/FAIL
                if "success_rate" in cond_data:
                    rate = cond_data["success_rate"]
                    ci = cond_data.get("ci_90")
                    if ci:
                        success = (
                            f"{cond_data['successes']}/{cond_data['total_valid_runs']} "
                            f"{rate:.0%} {self._format_ci(ci)}"
                        )
                    else:
                        success = f"{rate:.0%} ({cond_data['successes']}/{cond_data['total_valid_runs']})"
                else:
                    success = "PASS" if cond_data.get("success") else "FAIL"

                # Extract efficiency metrics via unified helper
                metrics = self._get_fix_metrics(cond_data)
                time_s = metrics["wall_clock_seconds"]
                tokens = metrics["tokens"]
                tool_calls = metrics["tool_calls"]
                lines_changed = metrics["lines_changed"]

                tokens_fmt = f"{tokens / 1000:.1f}k"

                # Deltas: none is baseline, shows "—"
                if cond_key == "none":
                    d_time = "\u2014"
                    d_tokens = "\u2014"
                else:
                    delta = deltas.get(cond_key, {})
                    d_time = delta.get("time_percent", "N/A")
                    d_tokens = delta.get("tokens_percent", "N/A")

                row = (
                    f"| {task_id} | {cond_key} | {success} | {time_s:.1f} | "
                    f"{tokens_fmt} | {tool_calls} | {lines_changed} | "
                    f"{d_time} | {d_tokens}"
                )

                if has_cis:
                    # Show IL vs none comparison on the intent_layer row
                    comparison = il_vs_none if cond_key == "intent_layer" else ""
                    row += f" | {comparison} |"
                else:
                    row += " |"

                lines.append(row)

            # Blank row between tasks
            blank = "|  |  |  |  |  |  |  |  |  |" + ("  |" if has_cis else "")
            lines.append(blank)

        # Remove trailing blank row
        if lines and lines[-1].strip().replace("|", "").replace(" ", "") == "":
            lines.pop()

        # Paired Analysis (McNemar's Test) section
        mcnemar_data = summary.get("mcnemar", {})
        if mcnemar_data and any(v["n_discordant"] > 0 for v in mcnemar_data.values()):
            lines += [
                "",
                "",
                "## Paired Analysis (McNemar's Test)",
                "",
                "| Comparison | Discordant | A wins | B wins | p-value | Sig. |",
                "|---|---|---|---|---|---|",
            ]
            for key, data in mcnemar_data.items():
                label = key.replace("_vs_", " vs ")
                sig = "*" if data["p_value"] < 0.05 else ""
                lines.append(
                    f"| {label} | {data['n_discordant']} | "
                    f"{data['a_wins']} | {data['b_wins']} | "
                    f"{data['p_value']:.3f} | {sig} |"
                )

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return str(path)
