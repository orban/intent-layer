# lib/reporter.py
from __future__ import annotations
import json
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.task_runner import TaskResult, Condition
from lib.stats import wilson_score_interval, ci_overlap, mcnemar_test, fisher_exact_test
from lib.budget import fmt_tokens


@dataclass
class EvalResults:
    eval_id: str
    timestamp: str
    results: list[dict[str, Any]]
    summary: dict[str, Any]
    budget: dict[str, Any] | None = None
    run_config: dict[str, Any] | None = None


class Reporter:
    # Display names for conditions in markdown output
    DISPLAY_NAMES = {
        "none": "None",
        "flat_llm": "Flat LLM",
        "intent_layer": "Intent Layer",
        "human": "Human",
        "test_after_edit": "Test After Edit",
    }

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _discover_conditions(compiled_results: list[dict]) -> list[str]:
        """Discover condition keys present in compiled result dicts.

        Returns baseline ("none") first if present, then remaining keys sorted.
        """
        skip = {"task_id", "deltas"}
        cond_keys: set[str] = set()
        for r in compiled_results:
            for key in r:
                if key not in skip and r[key] is not None:
                    cond_keys.add(key)
        # Baseline first, then alphabetical
        baseline = "none"
        rest = sorted(k for k in cond_keys if k != baseline)
        if baseline in cond_keys:
            return [baseline] + rest
        return rest

    @classmethod
    def _display_name(cls, cond_key: str) -> str:
        """Human-readable display name for a condition key."""
        return cls.DISPLAY_NAMES.get(cond_key, cond_key.replace("_", " ").title())

    def compile_results(
        self,
        results: list[TaskResult],
        preflight_budget: dict | None = None,
        postflight_budget: dict | None = None,
    ) -> EvalResults:
        """Compile task results into structured eval results.

        When repetitions > 1, groups multiple runs of the same task+condition
        and reports medians for efficiency metrics alongside success rates.
        Individual runs are preserved in a "runs" array.

        Budget snapshots (preflight/postflight) are passed in from cli.py —
        this module never shells out to external tools.
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

        # Discover conditions present in this run
        conditions_present = sorted(set(r.condition.value for r in results))
        baseline = Condition.NONE.value
        treatments = [c for c in conditions_present if c != baseline]

        compiled = []
        for task_id, conditions in grouped.items():
            task_result: dict[str, Any] = {"task_id": task_id}
            for cond_key in conditions_present:
                runs = conditions.get(cond_key, [])
                task_result[cond_key] = self._serialize_condition(runs) if runs else None

            baseline_runs = conditions.get(baseline, [])
            deltas = {}
            for treatment in treatments:
                deltas[treatment] = self._compute_delta(baseline_runs, conditions.get(treatment, []))
            task_result["deltas"] = deltas

            compiled.append(task_result)

        summary = self._compute_summary(results)

        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        eval_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")

        # Build budget snapshot: total tokens consumed + nightshift before/after
        total_tokens = sum(r.input_tokens + r.output_tokens for r in results)
        budget_data: dict[str, Any] | None = None
        if total_tokens > 0:
            budget_data = {"total_tokens_consumed": total_tokens}
            if preflight_budget:
                budget_data["nightshift_remaining_before"] = preflight_budget.get("remaining_tokens")
            if postflight_budget:
                budget_data["nightshift_remaining_after"] = postflight_budget.get("remaining_tokens")

        return EvalResults(
            eval_id=eval_id,
            timestamp=timestamp,
            results=compiled,
            summary=summary,
            budget=budget_data,
        )

    @staticmethod
    def _build_cost_breakdown(
        fix_cost_usd: float,
        skill_cost_usd: float = 0.0,
    ) -> dict[str, float]:
        return {
            "fix_only_usd": round(fix_cost_usd, 6),
            "skill_generation_usd": round(skill_cost_usd, 6),
            "total_usd": round(fix_cost_usd + skill_cost_usd, 6),
        }

    def _serialize_single_result(self, r: TaskResult) -> dict:
        """Serialize a single TaskResult to dict."""
        result = {
            "success": r.success,
            "rep": r.rep,
            "test_output": r.test_output[:1000],  # Truncate
            "cost_breakdown": self._build_cost_breakdown(
                r.cost_usd,
                r.skill_generation.cost_usd if r.skill_generation else 0.0,
            ),
        }

        if r.skill_generation:
            result["fix_only"] = {
                "wall_clock_seconds": r.wall_clock_seconds,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": round(r.cost_usd, 6),
                "tool_calls": r.tool_calls,
                "lines_changed": r.lines_changed,
                "files_touched": r.files_touched,
            }
            result["skill_generation"] = {
                "wall_clock_seconds": r.skill_generation.wall_clock_seconds,
                "input_tokens": r.skill_generation.input_tokens,
                "output_tokens": r.skill_generation.output_tokens,
                "cost_usd": round(r.skill_generation.cost_usd, 6),
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
                "cost_usd": round(r.cost_usd + r.skill_generation.cost_usd, 6),
            }
        else:
            result["wall_clock_seconds"] = r.wall_clock_seconds
            result["input_tokens"] = r.input_tokens
            result["output_tokens"] = r.output_tokens
            result["cost_usd"] = round(r.cost_usd, 6)
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
                "cost_usd": round(statistics.median(r.cost_usd for r in valid_runs), 6),
                "tool_calls": int(statistics.median(r.tool_calls for r in valid_runs)),
                "lines_changed": int(statistics.median(r.lines_changed for r in valid_runs)),
            }
            result["cost_breakdown"] = self._build_cost_breakdown(
                statistics.median(r.cost_usd for r in valid_runs),
                statistics.median(
                    r.skill_generation.cost_usd if r.skill_generation else 0.0
                    for r in valid_runs
                ),
            )
            result["cost_totals"] = self._build_cost_breakdown(
                sum(r.cost_usd for r in valid_runs),
                sum(
                    r.skill_generation.cost_usd if r.skill_generation else 0.0
                    for r in valid_runs
                ),
            )

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
                "cost_usd": m.get("cost_usd", 0.0),
                "tool_calls": m["tool_calls"],
                "lines_changed": m["lines_changed"],
            }
        # Single run with skill_generation
        if "fix_only" in cond_data:
            fix = cond_data["fix_only"]
            return {
                "wall_clock_seconds": fix["wall_clock_seconds"],
                "tokens": fix["input_tokens"] + fix["output_tokens"],
                "cost_usd": fix.get("cost_usd", 0.0),
                "tool_calls": fix["tool_calls"],
                "lines_changed": fix["lines_changed"],
            }
        # Single run without skill_generation
        return {
            "wall_clock_seconds": cond_data.get("wall_clock_seconds", 0),
            "tokens": cond_data.get("input_tokens", 0) + cond_data.get("output_tokens", 0),
            "cost_usd": cond_data.get("cost_usd", 0.0),
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
        b_cost = statistics.median(r.cost_usd for r in b_valid)
        t_cost = statistics.median(r.cost_usd for r in t_valid)
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
            "cost_percent": f"{pct(b_cost, t_cost):+.1f}%",
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

        Condition-agnostic: iterates over whatever conditions appear in results.
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

        conditions_present = sorted(set(r.condition for r in results), key=lambda c: c.value)
        per_cond = {c: [r for r in results if r.condition == c] for c in conditions_present}

        infra_errors = sum(1 for r in results if self._is_infra_error(r))

        def median_tokens(task_results: list[TaskResult]) -> int:
            """Median total tokens (input+output) for valid runs."""
            valid = [r for r in task_results if not self._is_infra_error(r)]
            if not valid:
                return 0
            return int(statistics.median(r.input_tokens + r.output_tokens for r in valid))

        def median_fix_cost(task_results: list[TaskResult]) -> float:
            valid = [r for r in task_results if not self._is_infra_error(r)]
            if not valid:
                return 0.0
            return round(statistics.median(r.cost_usd for r in valid), 6)

        def median_skill_cost(task_results: list[TaskResult]) -> float:
            valid = [r for r in task_results if not self._is_infra_error(r)]
            if not valid:
                return 0.0
            return round(
                statistics.median(
                    r.skill_generation.cost_usd if r.skill_generation else 0.0
                    for r in valid
                ),
                6,
            )

        def total_fix_cost(task_results: list[TaskResult]) -> float:
            valid = [r for r in task_results if not self._is_infra_error(r)]
            return round(sum(r.cost_usd for r in valid), 6)

        def total_skill_cost(task_results: list[TaskResult]) -> float:
            valid = [r for r in task_results if not self._is_infra_error(r)]
            return round(
                sum(r.skill_generation.cost_usd if r.skill_generation else 0.0 for r in valid),
                6,
            )

        summary: dict[str, Any] = {
            "total_tasks": len(set(r.task_id for r in results)),
            "infrastructure_errors": infra_errors,
        }

        for cond in conditions_present:
            label = cond.value
            cond_results = per_cond[cond]
            summary[f"{label}_success_rate"] = success_rate(cond_results)
            summary[f"{label}_itt_rate"] = itt_rate(cond_results)
            summary[f"{label}_median_tokens"] = median_tokens(cond_results)
            summary[f"{label}_median_cost_usd"] = median_fix_cost(cond_results)

        summary["cost_attribution"] = {"by_condition": {}, "overall": {}}
        overall_fix_cost = 0.0
        overall_skill_cost = 0.0
        for cond in conditions_present:
            label = cond.value
            cond_results = per_cond[cond]
            cond_fix_cost = total_fix_cost(cond_results)
            cond_skill_cost = total_skill_cost(cond_results)
            summary["cost_attribution"]["by_condition"][label] = {
                "median_fix_only_usd": median_fix_cost(cond_results),
                "median_skill_generation_usd": median_skill_cost(cond_results),
                "median_total_usd": round(
                    median_fix_cost(cond_results) + median_skill_cost(cond_results), 6
                ),
                "total_fix_only_usd": cond_fix_cost,
                "total_skill_generation_usd": cond_skill_cost,
                "total_usd": round(cond_fix_cost + cond_skill_cost, 6),
            }
            overall_fix_cost += cond_fix_cost
            overall_skill_cost += cond_skill_cost
        summary["cost_attribution"]["overall"] = {
            "total_fix_only_usd": round(overall_fix_cost, 6),
            "total_skill_generation_usd": round(overall_skill_cost, 6),
            "total_usd": round(overall_fix_cost + overall_skill_cost, 6),
        }

        # Add CIs when we have multi-run data
        has_multi_run = any(
            sum(1 for r2 in results if r2.task_id == r.task_id and r2.condition == r.condition) > 1
            for r in results
        )
        if has_multi_run:
            for cond in conditions_present:
                label = cond.value
                valid = [r for r in per_cond[cond] if not self._is_infra_error(r)]
                if valid:
                    successes = sum(1 for r in valid if r.success)
                    ci_lower, ci_upper, _ = wilson_score_interval(successes, len(valid), 0.90)
                    summary[f"{label}_ci_90"] = {
                        "lower": round(ci_lower, 3),
                        "upper": round(ci_upper, 3),
                    }

        # McNemar's paired analysis: compare conditions per (task, rep) pair
        summary["mcnemar"] = self._compute_mcnemar(results)

        # Derive significance flags from McNemar p-values (paired test).
        # Only for multi-run data — single-run has too few pairs to be meaningful.
        baseline = Condition.NONE
        treatments = [c for c in conditions_present if c != baseline]
        if has_multi_run:
            for treatment in treatments:
                key = f"{treatment.value}_vs_{baseline.value}"
                mcnemar_entry = summary["mcnemar"].get(key)
                if mcnemar_entry and mcnemar_entry["n_discordant"] > 0:
                    summary[f"{treatment.value}_vs_{baseline.value}_significant"] = mcnemar_entry["p_value"] < 0.05

        # Per-task Fisher's exact tests + recommendations
        if has_multi_run:
            per_task_fisher = self._compute_per_task_fisher(results)
            summary["per_task_fisher"] = per_task_fisher
            summary["recommendations"] = self._compute_recommendations(per_task_fisher, results)

        return summary

    def _compute_mcnemar(self, results: list[TaskResult]) -> dict:
        """Compute McNemar's test for each pair of conditions.

        Pairs results by (task_id, rep_index) where rep_index is derived
        from ordering within each (task_id, condition) group. Excludes
        pairs where either result is an infra error.
        """
        # Group by (task_id, condition), sorted by rep for deterministic pairing
        grouped: dict[str, dict[str, list[TaskResult]]] = {}
        for r in results:
            if r.task_id not in grouped:
                grouped[r.task_id] = {}
            cond = r.condition.value
            if cond not in grouped[r.task_id]:
                grouped[r.task_id][cond] = []
            grouped[r.task_id][cond].append(r)
        for conditions in grouped.values():
            for runs in conditions.values():
                runs.sort(key=lambda r: r.rep)

        # Generate all unique condition pairs: (treatment, baseline).
        # Use baseline-first ordering so keys read "treatment_vs_baseline".
        baseline = Condition.NONE.value
        cond_values = sorted(set(r.condition.value for r in results))
        comparisons = []
        for i, a in enumerate(cond_values):
            for b in cond_values[i + 1:]:
                # Ensure baseline is always the second element
                if a == baseline:
                    comparisons.append((b, a))
                elif b == baseline:
                    comparisons.append((a, b))
                else:
                    # Neither is baseline — alphabetical: later vs earlier
                    comparisons.append((b, a))

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

    def _compute_per_task_fisher(self, results: list[TaskResult]) -> list[dict]:
        """Run Fisher's exact test per task for each condition pair.

        Unlike McNemar (which pools all tasks for paired analysis), Fisher
        tests each task independently — useful for identifying which specific
        tasks drive the aggregate signal and for flagging task quality issues.
        """
        # Group by task_id → condition → list of valid results
        grouped: dict[str, dict[str, list[TaskResult]]] = {}
        for r in results:
            if self._is_infra_error(r):
                continue
            if r.task_id not in grouped:
                grouped[r.task_id] = {}
            cond = r.condition.value
            if cond not in grouped[r.task_id]:
                grouped[r.task_id][cond] = []
            grouped[r.task_id][cond].append(r)

        # Generate all unique condition pairs dynamically
        cond_values = sorted(set(
            r.condition.value for r in results if not self._is_infra_error(r)
        ))
        comparisons = []
        for i, a in enumerate(cond_values):
            for b in cond_values[i + 1:]:
                comparisons.append((a, b))

        per_task: list[dict] = []
        for task_id, conditions in grouped.items():
            task_entry: dict[str, Any] = {"task_id": task_id, "comparisons": {}}

            for cond_a, cond_b in comparisons:
                a_runs = conditions.get(cond_a, [])
                b_runs = conditions.get(cond_b, [])
                if not a_runs or not b_runs:
                    continue

                a_pass = sum(1 for r in a_runs if r.success)
                b_pass = sum(1 for r in b_runs if r.success)
                result = fisher_exact_test(a_pass, len(a_runs), b_pass, len(b_runs))
                task_entry["comparisons"][f"{cond_a}_vs_{cond_b}"] = result

            # Task quality flags
            all_runs = [r for runs in conditions.values() for r in runs]
            total_pass = sum(1 for r in all_runs if r.success)
            task_entry["total_runs"] = len(all_runs)
            task_entry["total_pass"] = total_pass
            task_entry["pass_rate"] = round(total_pass / len(all_runs), 2) if all_runs else 0

            # Ceiling: all conditions ~100% → no discriminative power
            task_entry["ceiling_effected"] = total_pass == len(all_runs) and len(all_runs) >= 3

            # Floor: all conditions 0% → task may be broken or too hard
            task_entry["floor_effected"] = total_pass == 0 and len(all_runs) >= 3

            per_task.append(task_entry)

        return per_task

    def _compute_recommendations(self, per_task_fisher: list[dict], results: list[TaskResult]) -> list[str]:
        """Generate actionable recommendations from per-task analysis."""
        recs: list[str] = []

        # Check for tasks with all infra errors (no valid runs)
        task_ids_with_data = {t["task_id"] for t in per_task_fisher}
        all_task_ids = set(r.task_id for r in results)
        infra_only = all_task_ids - task_ids_with_data
        for tid in sorted(infra_only):
            recs.append(f"**{tid}**: all runs were infrastructure errors. Check Docker setup and pre-validation.")

        for t in per_task_fisher:
            tid = t["task_id"]
            if t["ceiling_effected"]:
                recs.append(
                    f"**{tid}**: ceiling-effected ({t['total_pass']}/{t['total_runs']} pass). "
                    f"No discriminative power — consider replacing with a harder task."
                )
            if t["floor_effected"]:
                recs.append(
                    f"**{tid}**: floor-effected (0/{t['total_runs']} pass). "
                    f"All conditions fail — task may be too hard or misconfigured."
                )

            # Flag significant per-task results
            for comp_key, comp in t["comparisons"].items():
                if comp["p_value"] < 0.10 and abs(comp["rate_diff"]) >= 0.3:
                    direction = "+" if comp["rate_diff"] > 0 else ""
                    recs.append(
                        f"**{tid}** ({comp_key.replace('_vs_', ' vs ')}): "
                        f"{direction}{comp['rate_diff']:.0%} rate difference "
                        f"(p={comp['p_value']:.3f}). Worth deeper investigation."
                    )

        return recs

    def write_checkpoint(
        self,
        results: list['TaskResult'],
        eval_id: str,
        run_config: dict | None = None,
    ) -> str:
        """Write incremental checkpoint after each task result.

        Produces a --resume-compatible JSON file so that a killed run can
        be continued with the same command plus --resume <checkpoint>.
        The checkpoint is overwritten after each result, keeping only the
        latest snapshot.

        run_config: snapshot of the CLI flags (tasks, conditions, reps, timeout)
        so --resume can detect incompatible configs before mixing results.
        """
        checkpoint_path = self.output_dir / f"in-progress-{eval_id}.json"
        compiled = self.compile_results(results)
        # Stamp with the pre-assigned eval_id so resume traces lineage
        data = asdict(compiled)
        data["eval_id"] = eval_id
        data["checkpoint"] = True
        data["completed_runs"] = len(results)
        if run_config is not None:
            data["run_config"] = run_config

        # Atomic write: write to tmp then rename to avoid partial reads
        tmp_path = checkpoint_path.with_suffix(f".tmp.{id(results)}")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        tmp_path.rename(checkpoint_path)

        return str(checkpoint_path)

    def remove_checkpoint(self, eval_id: str) -> None:
        """Remove checkpoint file after successful completion."""
        checkpoint_path = self.output_dir / f"in-progress-{eval_id}.json"
        checkpoint_path.unlink(missing_ok=True)

    def write_trial(self, result: 'TaskResult') -> str:
        """Write a per-trial result file for ls-level observability.

        Creates results/trials/<task_id>-<condition>-r<rep>.json so you
        can see exactly which trials completed by listing a directory.
        Each file is small (~1KB) and written atomically.
        """
        trials_dir = self.output_dir / "trials"
        trials_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{result.task_id}-{result.condition.value}-r{result.rep}.json"
        trial_path = trials_dir / filename

        data = {
            "task_id": result.task_id,
            "condition": result.condition.value,
            "rep": result.rep,
            "success": result.success,
            "wall_clock_seconds": result.wall_clock_seconds,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": round(result.cost_usd, 6),
            "tool_calls": result.tool_calls,
            "lines_changed": result.lines_changed,
            "cost_breakdown": self._build_cost_breakdown(
                result.cost_usd,
                result.skill_generation.cost_usd if result.skill_generation else 0.0,
            ),
        }
        if result.error:
            data["error"] = result.error
            data["error_class"] = (
                "infra" if result.error.startswith(self.INFRA_ERROR_PREFIXES)
                else "timeout" if result.error.startswith("[timeout]")
                else "genuine"
            )

        # Atomic write
        import os
        tmp_path = trial_path.with_suffix(f".tmp.{os.getpid()}")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        tmp_path.rename(trial_path)

        return str(trial_path)

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

        # Discover conditions from the compiled results
        cond_keys = self._discover_conditions(results.results)
        baseline = Condition.NONE.value
        treatments = [c for c in cond_keys if c != baseline]
        has_cis = any(f"{c}_ci_90" in summary for c in cond_keys)

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
        for label in cond_keys:
            display = self._display_name(label)
            rate = summary.get(f"{label}_success_rate", 0)
            ci = summary.get(f"{label}_ci_90")
            if ci:
                lines.append(
                    f"- **{display} success rate:** {rate:.0%} "
                    f"90% CI {self._format_ci(ci)}"
                )
            else:
                lines.append(f"- **{display} success rate:** {rate:.0%}")

        # Per-condition median token usage
        baseline_tok = summary.get(f"{baseline}_median_tokens", 0)
        if baseline_tok:
            lines.append("")
            lines.append("**Median tokens (input+output, fix phase only):**")
            for label in cond_keys:
                display = self._display_name(label)
                tok = summary.get(f"{label}_median_tokens", 0)
                tok_fmt = f"{tok / 1000:.0f}k" if tok else "N/A"
                if label == baseline or not baseline_tok:
                    lines.append(f"- **{display}:** {tok_fmt}")
                else:
                    pct_diff = (tok - baseline_tok) / baseline_tok * 100
                    lines.append(f"- **{display}:** {tok_fmt} ({pct_diff:+.0f}% vs {baseline})")

        cost_summary = summary.get("cost_attribution", {})
        by_condition = cost_summary.get("by_condition", {})
        overall_cost = cost_summary.get("overall", {})
        if by_condition:
            lines.append("")
            lines.append("**Estimated cost attribution (USD):**")
            for label in cond_keys:
                display = self._display_name(label)
                cond_cost = by_condition.get(label, {})
                lines.append(
                    f"- **{display}:** fix ${cond_cost.get('total_fix_only_usd', 0.0):.4f}, "
                    f"skill_generation ${cond_cost.get('total_skill_generation_usd', 0.0):.4f}, "
                    f"total ${cond_cost.get('total_usd', 0.0):.4f}"
                )
            lines.append(
                f"- **Overall:** fix ${overall_cost.get('total_fix_only_usd', 0.0):.4f}, "
                f"skill_generation ${overall_cost.get('total_skill_generation_usd', 0.0):.4f}, "
                f"total ${overall_cost.get('total_usd', 0.0):.4f}"
            )

        # Significance flags
        if has_cis:
            lines.append("")
            mcnemar_data = summary.get("mcnemar", {})
            for treatment in treatments:
                display = self._display_name(treatment)
                sig_key = f"{treatment}_vs_{baseline}_significant"
                mcnemar_entry = mcnemar_data.get(f"{treatment}_vs_{baseline}")
                if sig_key in summary and mcnemar_entry:
                    p = mcnemar_entry["p_value"]
                    n_disc = mcnemar_entry["n_discordant"]
                    if summary[sig_key]:
                        lines.append(f"- **{display} vs {self._display_name(baseline)}:** significant (McNemar p={p:.3f}, {n_disc} discordant pairs)")
                    else:
                        lines.append(f"- **{display} vs {self._display_name(baseline)}:** not significant (McNemar p={p:.3f}, {n_disc} discordant pairs)")

            # CI width as variance proxy
            widths = []
            for label in cond_keys:
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

        # Table header
        lines.append(
            "| Task | Condition | Success | Time (s) | Tokens | Tool Calls | Lines "
            "| Cost (USD) | \u0394 Time | \u0394 Tokens | \u0394 Cost |"
        )
        lines.append(
            "|------|-----------|---------|----------|--------|------------|-------"
            "|------------|--------|----------|--------|"
        )

        for r in results.results:
            task_id = r["task_id"]
            deltas = r.get("deltas", {})

            for cond_key in cond_keys:
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
                cost_usd = metrics["cost_usd"]
                tool_calls = metrics["tool_calls"]
                lines_changed = metrics["lines_changed"]

                tokens_fmt = f"{tokens / 1000:.1f}k"
                cost_fmt = f"${cost_usd:.4f}"

                # Deltas: baseline shows "—"
                if cond_key == baseline:
                    d_time = "\u2014"
                    d_tokens = "\u2014"
                    d_cost = "\u2014"
                else:
                    delta = deltas.get(cond_key, {})
                    d_time = delta.get("time_percent", "N/A")
                    d_tokens = delta.get("tokens_percent", "N/A")
                    d_cost = delta.get("cost_percent", "N/A")

                row = (
                    f"| {task_id} | {cond_key} | {success} | {time_s:.1f} | "
                    f"{tokens_fmt} | {tool_calls} | {lines_changed} | "
                    f"{cost_fmt} | {d_time} | {d_tokens} | {d_cost} |"
                )

                lines.append(row)

            # Blank row between tasks
            lines.append("|  |  |  |  |  |  |  |  |  |  |  |")

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

        # Per-Task Fisher's Exact Test section
        per_task_fisher = summary.get("per_task_fisher", [])
        tasks_with_comparisons = [t for t in per_task_fisher if t["comparisons"]]
        if tasks_with_comparisons:
            lines += [
                "",
                "",
                "## Per-Task Analysis (Fisher's Exact Test)",
                "",
                "| Task | Comparison | A rate | B rate | Diff | p-value | Sig. |",
                "|------|------------|--------|--------|------|---------|------|",
            ]
            for t in tasks_with_comparisons:
                tid = t["task_id"]
                for comp_key, comp in t["comparisons"].items():
                    label = comp_key.replace("_vs_", " vs ")
                    sig = "*" if comp["p_value"] < 0.05 else ("~" if comp["p_value"] < 0.10 else "")
                    lines.append(
                        f"| {tid} | {label} | {comp['a_rate']:.0%} | "
                        f"{comp['b_rate']:.0%} | {comp['rate_diff']:+.0%} | "
                        f"{comp['p_value']:.3f} | {sig} |"
                    )

            # Quality flags
            ceiling = [t for t in per_task_fisher if t["ceiling_effected"]]
            floor = [t for t in per_task_fisher if t["floor_effected"]]
            if ceiling or floor:
                lines.append("")
                for t in ceiling:
                    lines.append(f"- **{t['task_id']}**: ceiling-effected (100% all conditions)")
                for t in floor:
                    lines.append(f"- **{t['task_id']}**: floor-effected (0% all conditions)")

        # Recommendations section
        recs = summary.get("recommendations", [])
        if recs:
            lines += [
                "",
                "",
                "## Recommendations",
                "",
            ]
            for rec in recs:
                lines.append(f"- {rec}")

        # Budget Impact section (when budget data is available)
        if results.budget:
            try:
                b = results.budget
                total = b.get("total_tokens_consumed", 0)

                lines += ["", "", "## Budget Impact", "", f"- **Total tokens consumed:** {fmt_tokens(total)}"]

                before = b.get("nightshift_remaining_before")
                if isinstance(before, (int, float)):
                    lines.append(f"- **Nightshift remaining (before run):** {fmt_tokens(before)}")

                after = b.get("nightshift_remaining_after")
                if isinstance(after, (int, float)):
                    lines.append(f"- **Nightshift remaining (after run):** {fmt_tokens(after)}")

                if isinstance(before, (int, float)) and before > 0:
                    pct = total / before * 100
                    lines.append(f"- **Budget consumed by this run:** {pct:.1f}%")
            except (TypeError, ValueError, KeyError):
                pass  # Budget section is advisory — skip on any data issue

        with open(path, "w") as f:
            f.write("\n".join(lines))

        return str(path)
