# lib/cli.py
from __future__ import annotations
import json
import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import click

from lib.models import TaskFile
from lib.task_runner import TaskRunner, TaskResult, Condition, PreValidationCache
from lib.reporter import Reporter, EvalResults
from lib.stats import wilson_score_interval
from lib.git_scanner import GitScanner
from lib.git_ops import clone_repo, checkout_commit
from lib.index_cache import IndexCache
from lib.budget import check_budget, get_budget_status, refresh_budget_snapshot, fmt_tokens
from lib.agentbench_loader import load_instances, AgentbenchInstance
from lib.agentbench_runner import run_single as agentbench_run_single


# Thread-safe print lock for progress output
_print_lock = threading.Lock()


def _load_prior_results(json_path: str) -> tuple[set[tuple[str, str]], set[tuple[str, str]], dict]:
    """Load prior results JSON and classify (task_id, condition) pairs.

    Returns:
        passed: pairs where success=True and no error (carry forward)
        genuine_failures: pairs that failed due to test failures, not infra
            (skip by default on resume — retrying won't help)
        data: raw prior data dict

    Works for both single-run and multi-run formats:
    - Single-run: checks top-level success + absence of error
    - Multi-run: checks aggregate success (majority pass)

    Classification:
    - passed: success=True, no error → carry forward
    - infra error: error starts with INFRA_ERROR_PREFIXES → retry
    - genuine failure: everything else (test failures, timeouts) → skip by default
    """
    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in {json_path}: {e}")

    if not isinstance(data, dict) or "results" not in data:
        raise click.ClickException(f"Invalid results file: missing 'results' key in {json_path}")

    if not isinstance(data["results"], list):
        raise click.ClickException(f"Invalid results file: 'results' must be a list in {json_path}")

    passed = set()
    genuine_failures = set()

    for i, task in enumerate(data["results"]):
        if not isinstance(task, dict) or "task_id" not in task:
            raise click.ClickException(
                f"Invalid results file: task at index {i} missing 'task_id' in {json_path}"
            )
        task_id = task["task_id"]
        # Discover condition keys dynamically from prior results
        cond_keys = Reporter._discover_conditions([task])
        for cond_key in cond_keys:
            cond_data = task.get(cond_key)
            if cond_data is None:
                continue

            if cond_data.get("success") is True and "error" not in cond_data:
                passed.add((task_id, cond_key))
                continue

            # Not passed — classify as infra error or genuine failure.
            # Multi-run: if any individual run had an infra error, the
            # whole condition is worth retrying (more valid runs = better stats).
            is_infra = _is_infra_error_dict(cond_data)
            if not is_infra and "runs" in cond_data:
                is_infra = any(
                    r.get("error", "").startswith(Reporter.INFRA_ERROR_PREFIXES)
                    for r in cond_data["runs"]
                )

            if not is_infra:
                genuine_failures.add((task_id, cond_key))

    return passed, genuine_failures, data


def _is_infra_error_dict(cond_data: dict) -> bool:
    """Check if a condition dict represents an infrastructure error."""
    error = cond_data.get("error")
    if error is None:
        return False
    return error.startswith(Reporter.INFRA_ERROR_PREFIXES)


def _merge_results(new_results: 'EvalResults', prior_data: dict, passed_pairs: set[tuple[str, str]]) -> 'EvalResults':
    """Merge new execution results with carried-forward prior results.

    For each task in the prior data:
    - Conditions in passed_pairs are kept from prior data
    - Conditions that were re-run are replaced with new compilation
    - Mixed tasks (some kept, some re-run) get deltas cleared
    Tasks not in prior data are included from new results directly.
    """
    # Index new results by task_id
    new_by_task = {r["task_id"]: r for r in new_results.results}

    # Index prior results by task_id
    prior_by_task = {r["task_id"]: r for r in prior_data["results"]}

    # Precompute task IDs that have at least one carried-forward condition
    passed_task_ids = {tid for tid, _ in passed_pairs}

    # All task_ids in order (prior order first, then any new-only tasks)
    seen = set()
    task_order = []
    for r in prior_data["results"]:
        task_order.append(r["task_id"])
        seen.add(r["task_id"])
    for r in new_results.results:
        if r["task_id"] not in seen:
            task_order.append(r["task_id"])
            seen.add(r["task_id"])

    merged = []
    for task_id in task_order:
        prior_task = prior_by_task.get(task_id)
        new_task = new_by_task.get(task_id)

        if prior_task is None:
            # Entirely new task — use new results as-is
            if new_task:
                merged.append(new_task)
            continue

        if new_task is None and task_id not in passed_task_ids:
            # Prior task that wasn't in the new run and had no passed pairs — skip
            continue

        # Build merged task by picking condition blocks from prior or new
        merged_task = {"task_id": task_id}
        has_carried = False  # Any condition kept from prior via passed_pairs
        has_new = False  # Any condition replaced with new results
        # Discover conditions from both prior and new task dicts
        all_cond_keys = Reporter._discover_conditions(
            [t for t in (prior_task, new_task) if t is not None]
        )
        for cond_key in all_cond_keys:
            if (task_id, cond_key) in passed_pairs:
                # Carry forward from prior
                merged_task[cond_key] = prior_task.get(cond_key)
                has_carried = True
            elif new_task and new_task.get(cond_key) is not None:
                # Use new result
                merged_task[cond_key] = new_task[cond_key]
                has_new = True
            else:
                # Keep prior (even if failed — it wasn't re-run)
                merged_task[cond_key] = prior_task.get(cond_key)
        has_mixed = has_carried and has_new

        # Deltas: use new if fully re-run, clear for mixed tasks
        if has_mixed:
            merged_task["deltas"] = {"note": "mixed resume — deltas not recomputed"}
        elif new_task and "deltas" in new_task:
            merged_task["deltas"] = new_task["deltas"]
        else:
            merged_task["deltas"] = prior_task.get("deltas", {})

        merged.append(merged_task)

    # Recompute summary from merged results
    summary = _recompute_summary(merged)

    return replace(
        new_results,
        results=merged,
        summary=summary,
        eval_id=new_results.eval_id,
        timestamp=new_results.timestamp,
    )


def _recompute_summary(merged_results: list[dict]) -> dict:
    """Recompute summary stats from merged result dicts.

    Mirrors Reporter._compute_summary: success rates and Wilson Score CIs
    for multi-run data. Significance flags (from McNemar) are NOT recomputed
    here — they are carried forward from the original compilation.
    """
    # Discover conditions dynamically from the merged data
    conditions_present = Reporter._discover_conditions(merged_results)
    cond_stats: dict[str, dict] = {
        c: {"successes": 0, "total": 0, "assigned": 0}
        for c in conditions_present
    }
    infra_errors = 0
    has_multi_run = False

    for task in merged_results:
        for cond_key in conditions_present:
            cond_data = task.get(cond_key)
            if cond_data is None:
                continue

            if "runs" in cond_data:
                has_multi_run = True
                valid = cond_data.get("total_valid_runs", 0)
                successes = cond_data.get("successes", 0)
                total_runs = len(cond_data["runs"])
                infra_errors += total_runs - valid
                cond_stats[cond_key]["successes"] += successes
                cond_stats[cond_key]["total"] += valid
                cond_stats[cond_key]["assigned"] += total_runs
            else:
                cond_stats[cond_key]["assigned"] += 1
                if _is_infra_error_dict(cond_data):
                    infra_errors += 1
                else:
                    cond_stats[cond_key]["total"] += 1
                    if cond_data.get("success") is True:
                        cond_stats[cond_key]["successes"] += 1

    def rate(stats):
        if stats["total"] == 0:
            return 0
        return round(stats["successes"] / stats["total"], 2)

    def itt_rate(stats):
        if stats["assigned"] == 0:
            return 0
        return round(stats["successes"] / stats["assigned"], 2)

    summary: dict = {
        "total_tasks": len(merged_results),
        "infrastructure_errors": infra_errors,
        "resumed_from": None,  # Filled in by caller
    }
    for label in conditions_present:
        summary[f"{label}_success_rate"] = rate(cond_stats[label])
        summary[f"{label}_itt_rate"] = itt_rate(cond_stats[label])

    # Add Wilson Score CIs when multi-run data is present
    if has_multi_run:
        for label in conditions_present:
            stats = cond_stats[label]
            if stats["total"] > 0:
                ci_lower, ci_upper, _ = wilson_score_interval(
                    stats["successes"], stats["total"], 0.90
                )
                summary[f"{label}_ci_90"] = {
                    "lower": round(ci_lower, 3),
                    "upper": round(ci_upper, 3),
                }

        # Note: significance flags are derived from McNemar in the reporter's
        # _compute_summary. _recompute_summary doesn't have access to raw
        # TaskResults for McNemar pairing, so significance flags from merged
        # results are carried forward from the original compilation.

    return summary


def _load_pre_validated_tasks(prior_data: dict) -> frozenset[str]:
    """Identify tasks that passed pre-validation in a prior run.

    A task passed pre-validation if any condition's error does NOT start
    with "[pre-validation]" — meaning Claude ran, tests ran, or it
    succeeded, all of which happen after pre-validation.
    """
    validated = set()
    for task in prior_data.get("results", []):
        task_id = task.get("task_id")
        if not task_id:
            continue
        for cond_key in Reporter._discover_conditions([task]):
            cond = task.get(cond_key)
            if cond is None:
                continue
            error = cond.get("error", "")
            if not error.startswith("[pre-validation]"):
                validated.add(task_id)
                break
    return frozenset(validated)


def _make_progress_callback(verbose: bool):
    """Create a progress callback that prints to stderr if verbose is enabled."""
    if not verbose:
        return None

    def callback(task_id: str, condition: str, step: str, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Truncate task_id for readability
        short_id = task_id[:30] + "..." if len(task_id) > 33 else task_id
        with _print_lock:
            click.echo(f"  [{timestamp}] {short_id} ({condition}) [{step}] {message}", err=True)

    return callback


def _create_reference_clones(
    repo_urls: set[str], workspaces_dir: Path
) -> dict[str, str]:
    """Create one full network clone per unique repo for local hardlink clones."""
    reference_clones: dict[str, str] = {}
    reference_dir = workspaces_dir / ".references"
    for repo_url in repo_urls:
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        ref_path = reference_dir / repo_name
        if not ref_path.exists():
            click.echo(f"Creating reference clone for {repo_name}...")
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            clone_repo(repo_url, str(ref_path), shallow=False)
        reference_clones[repo_url] = str(ref_path)
    return reference_clones


@click.group()
def main():
    """A/B/C eval harness for Claude skills."""
    pass


@main.command()
@click.option("--repo", required=True, help="Repository URL to scan")
@click.option("--output", "-o", required=True, help="Output YAML file path")
@click.option("--since", help="Only scan commits since date (YYYY-MM-DD)")
@click.option("--limit", default=50, help="Max tasks to find")
@click.option("--docker-image", default="node:20-slim", help="Docker image for this repo")
@click.option("--setup", multiple=True, default=["npm install"], help="Setup commands")
@click.option("--test-command", default="npm test", help="Test command")
@click.option("--branch", default="main", help="Default branch")
def scan(repo, output, since, limit, docker_image, setup, test_command, branch):
    """Scan a repo for bug fix commits and generate task YAML."""
    click.echo(f"Scanning {repo}...")

    with tempfile.TemporaryDirectory() as tmp:
        click.echo("Cloning repository...")
        clone_repo(repo, tmp, shallow=False)

        scanner = GitScanner()
        tasks = scanner.scan_repo(tmp, since=since, limit=limit)

        click.echo(f"Found {len(tasks)} bug fix commits")

        yaml_content = scanner.generate_yaml(
            tasks=tasks,
            repo_url=repo,
            docker_image=docker_image,
            setup=list(setup),
            test_command=test_command,
            default_branch=branch
        )

        Path(output).write_text(yaml_content)
        click.echo(f"Wrote {output}")


@main.command()
@click.option("--tasks", "-t", multiple=True, required=True, help="Task YAML files")
@click.option("--parallel", "-p", default=8, help="Number of parallel workers")
@click.option("--category", type=click.Choice(["simple_fix", "targeted_refactor", "complex_fix"]))
@click.option("--output", "-o", default="results", help="Output directory")
@click.option("--keep-workspaces", is_flag=True, help="Don't cleanup workspaces")
@click.option("--dry-run", is_flag=True, help="Show what would run")
@click.option("--timeout", default=1800, help="Per-task timeout in seconds")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress for each step")
@click.option("--clear-cache", is_flag=True, help="Clear index cache before running")
@click.option("--no-cache", is_flag=True, help="Disable index caching entirely")
@click.option("--cache-dir", default="workspaces/.index-cache", help="Index cache directory")
@click.option("--condition", "-c", multiple=True,
              type=click.Choice([c.value for c in Condition]),
              help="Conditions to run (default: none, flat_llm, intent_layer)")
@click.option("--model", default="sonnet",
              help="Claude model to use (default: sonnet)")
@click.option("--repetitions", "-n", default=1,
              help="Number of times to repeat each task/condition pair (default: 1)")
@click.option("--resume", default=None, type=click.Path(exists=True),
              help="Prior results JSON — skip passed pairs, re-run infra errors")
@click.option("--retry-all", is_flag=True,
              help="With --resume: also retry genuine failures, not just infra errors")
def run(tasks, parallel, category, output, keep_workspaces, dry_run, timeout, verbose, clear_cache, no_cache, cache_dir, condition, model, repetitions, resume, retry_all):
    """Run eval on task files."""
    # Validate task files exist
    for task_path in tasks:
        if not Path(task_path).exists():
            raise click.ClickException(f"Task file does not exist: {task_path}")

    # Load all task files
    all_tasks = []
    for task_path in tasks:
        task_file = TaskFile.from_yaml(Path(task_path))
        for task in task_file.tasks:
            if category and task.category != category:
                continue
            all_tasks.append((task_file.repo, task))

    click.echo(f"Loaded {len(all_tasks)} tasks from {len(tasks)} file(s)")

    # Handle cache management (do this before dry-run check)
    if clear_cache and not no_cache:
        cache = IndexCache(cache_dir)
        cache.clear()
        click.echo(f"Cleared index cache at {cache_dir}")

    # Determine conditions to run (HUMAN is AGENTbench-only, not used here)
    YAML_CONDITIONS = [Condition.NONE, Condition.FLAT_LLM, Condition.INTENT_LAYER]
    if condition:
        conditions = [Condition(c) for c in condition]
    else:
        conditions = YAML_CONDITIONS

    # Build work queue (with repetitions)
    work_queue = []
    for repo, task in all_tasks:
        for cond in conditions:
            for rep in range(repetitions):
                work_queue.append((repo, task, cond, rep))

    # Filter out passed pairs from prior run
    passed_pairs = set()
    genuine_fail_pairs = set()
    prior_data = None
    pre_validated_tasks: frozenset[str] = frozenset()
    if resume:
        passed_pairs, genuine_fail_pairs, prior_data = _load_prior_results(resume)
        pre_validated_tasks = _load_pre_validated_tasks(prior_data)

        # Config compatibility check: warn if prior run used different settings
        prior_config = prior_data.get("run_config")
        if prior_config:
            mismatches = []
            current_task_ids = sorted(set(t.id for _, t in all_tasks))
            prior_task_ids = sorted(prior_config.get("task_ids", []))
            if current_task_ids != prior_task_ids:
                mismatches.append(f"tasks: {len(prior_task_ids)} prior vs {len(current_task_ids)} current")
            if prior_config.get("repetitions") != repetitions:
                mismatches.append(f"repetitions: {prior_config['repetitions']} prior vs {repetitions} current")
            if prior_config.get("timeout") != timeout:
                mismatches.append(f"timeout: {prior_config['timeout']} prior vs {timeout} current")
            prior_conds = sorted(prior_config.get("conditions", []))
            current_conds = sorted(c.value for c in conditions)
            if prior_conds != current_conds:
                mismatches.append(f"conditions: {prior_conds} prior vs {current_conds} current")
            if mismatches:
                click.echo(f"\u26a0 Config mismatch with prior run ({', '.join(mismatches)})")

        # By default, skip both passed pairs AND genuine failures.
        # Genuine failures (test ran, code didn't fix it) won't improve on retry.
        # Only infra errors (harness/Docker/network problems) are retried.
        # Use --retry-all to also retry genuine failures.
        skip_pairs = passed_pairs.copy()
        if not retry_all:
            skip_pairs |= genuine_fail_pairs

        original_len = len(work_queue)
        work_queue = [item for item in work_queue if (item[1].id, item[2].value) not in skip_pairs]
        n_infra = original_len - len(work_queue) - len(passed_pairs) - (len(genuine_fail_pairs) if not retry_all else 0)

        click.echo(f"Resume: {len(passed_pairs)} passed (carried forward), "
                   f"{len(genuine_fail_pairs)} genuine failures ({'retrying' if retry_all else 'skipped'}), "
                   f"{len(work_queue)} to re-run")
        if pre_validated_tasks:
            click.echo(f"Resume: {len(pre_validated_tasks)} task(s) will skip pre-validation")

    if dry_run:
        click.echo("\nDry run - would execute:")
        for _repo, task, cond, rep in work_queue:
            rep_tag = f" [rep {rep+1}]" if repetitions > 1 else ""
            click.echo(f"  - {task.id} ({cond.value}){rep_tag}")
        if not work_queue:
            click.echo("  (nothing to re-run)")
        return

    total_unique = len(set((item[1].id, item[2].value) for item in work_queue))
    rep_note = f" x{repetitions} reps" if repetitions > 1 else ""
    click.echo(f"Running {total_unique} task/condition pairs{rep_note} ({len(work_queue)} total) with {parallel} workers")
    if verbose:
        click.echo("Verbose mode: showing detailed progress", err=True)

    # Pre-flight budget check (advisory — never blocks the run)
    # Single get_budget_status() call — reused for check_budget and post-run comparison
    preflight_budget = get_budget_status()
    budget_warning = check_budget(len(work_queue), status=preflight_budget)
    if budget_warning:
        click.echo(f"\n\u26a0 {budget_warning}\n")

    workspaces_dir = Path("workspaces")
    results = []
    progress_callback = _make_progress_callback(verbose)

    # Phase 0: Create reference clones — one full network clone per unique repo.
    # Subsequent clones (warmup + task runs) use --local hardlinks from here,
    # turning ~5-10s network clones into <1s local copies.
    unique_repos = {repo.url for repo, _task in all_tasks}
    reference_clones = _create_reference_clones(unique_repos, workspaces_dir)

    # Shared pre-validation cache — identical Docker test runs across conditions
    # for the same task are deduplicated (saves ~16 Docker runs for 8 tasks x 3 conds).
    pre_val_cache = PreValidationCache()

    # Phase 1: Pre-warm cache — generate context files once per repo+condition.
    # Context files describe repo structure/conventions, which are stable across
    # nearby commits. So we generate once per repo, not per task commit.
    # This runs serially before the parallel task loop so each generation gets
    # the full timeout budget. Task runs then get instant cache hits.
    if not no_cache:
        # Collect unique (repo_url, condition) pairs that need generation.
        warmup_items: dict[tuple[str, str], 'RepoConfig'] = {}
        for repo, task in all_tasks:
            for cond in conditions:
                if cond == Condition.NONE:
                    continue
                key = (repo.url, cond.value)
                if key not in warmup_items:
                    warmup_items[key] = repo

        if warmup_items:
            click.echo(f"Pre-warming cache for {len(warmup_items)} repo/condition pair(s) in parallel...")
            # Single shared IndexCache so the threading.Lock serializes
            # concurrent save() calls across warmup threads.
            shared_cache = IndexCache(cache_dir)

            def _warmup_one(item):
                (repo_url, cond_str), repo_config = item
                cond = Condition(cond_str)
                runner = TaskRunner(
                    repo_config,
                    str(workspaces_dir),
                    progress_callback=progress_callback,
                    cache_dir=cache_dir,
                    use_cache=True,
                    reference_clone=reference_clones.get(repo_url),
                )
                runner.index_cache = shared_cache
                return runner.warm_cache(repo_url, cond, model=model)

            with ThreadPoolExecutor(max_workers=len(warmup_items)) as warmup_executor:
                warmup_futures = {
                    warmup_executor.submit(_warmup_one, item): item
                    for item in warmup_items.items()
                }
                for future in as_completed(warmup_futures):
                    (repo_url, cond_str), _ = warmup_futures[future]
                    try:
                        metrics = future.result()
                        if metrics and not metrics.cache_hit:
                            click.echo(f"  {cond_str}: generated {len(metrics.files_created)} file(s) in {metrics.wall_clock_seconds:.1f}s")
                        else:
                            click.echo(f"  {cond_str}: already cached")
                    except Exception as e:
                        click.echo(f"  {cond_str}: warmup failed - {e}", err=True)
                        click.echo(f"    (task runs will retry with their own timeout)", err=True)

    # Circuit breaker: stop retrying after repeated identical failures.
    # Pre-validation failures trip at task level (all conditions share Docker
    # setup), other failures trip at task+condition level.
    _cb_counts: dict[tuple[str, ...], int] = {}
    _cb_tripped: set[tuple[str, ...]] = set()
    _cb_lock = threading.Lock()
    CB_THRESHOLD = 2  # trip after this many consecutive failures

    def _cb_record(task_id: str, condition: str, error: str) -> bool:
        """Record a failure. Returns True if newly tripped."""
        with _cb_lock:
            if "[pre-validation]" in error:
                key = (task_id,)  # task-level — affects all conditions
            else:
                key = (task_id, condition)
            _cb_counts[key] = _cb_counts.get(key, 0) + 1
            if _cb_counts[key] >= CB_THRESHOLD:
                newly = key not in _cb_tripped
                _cb_tripped.add(key)
                return newly
        return False

    def _cb_is_tripped(task_id: str, condition: str) -> bool:
        with _cb_lock:
            return (task_id,) in _cb_tripped or (task_id, condition) in _cb_tripped

    def run_single(item):
        repo, task, condition, rep = item

        # Skip if circuit breaker already tripped for this task/condition
        if _cb_is_tripped(task.id, condition.value):
            return TaskResult(
                task_id=task.id,
                condition=condition,
                success=False,
                test_output="",
                wall_clock_seconds=0,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                lines_changed=0,
                files_touched=[],
                rep=rep,
                error=f"[circuit-breaker] skipped — repeated failures for this task"
            )

        runner = TaskRunner(
            repo,
            str(workspaces_dir),
            progress_callback=progress_callback,
            cache_dir=cache_dir,
            use_cache=not no_cache,
            reference_clone=reference_clones.get(repo.url),
            pre_val_cache=pre_val_cache,
            claude_timeout=timeout,
            skip_pre_validation_for=pre_validated_tasks,
        )
        result = runner.run(task, condition, model=model, rep=rep)

        if result.error:
            newly_tripped = _cb_record(task.id, condition.value, result.error)
            if newly_tripped:
                scope = task.id if "[pre-validation]" in result.error else f"{task.id}/{condition.value}"
                click.echo(f"  \u26a1 Circuit breaker tripped for {scope} — skipping remaining reps")

        return result

    # Mid-run budget tracking state
    budget_threshold = None
    if preflight_budget and preflight_budget.get("remaining_tokens"):
        budget_threshold = int(preflight_budget["remaining_tokens"] * 0.8)
    budget_warned = False

    # Pre-create reporter for incremental checkpoints.
    # eval_id assigned now so checkpoint filenames are stable across the run.
    reporter = Reporter(output)
    eval_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    # Snapshot run config for checkpoint verification on --resume
    run_config = {
        "task_ids": sorted(set(t.id for _, t in all_tasks)),
        "conditions": sorted(c.value for c in conditions),
        "repetitions": repetitions,
        "timeout": timeout,
        "model": model,
        "task_files": [str(Path(t).resolve()) for t in tasks],
    }

    # ── Control plane ─────────────────────────────────────────────
    control_dir = Path(output) / ".eval-control"
    control_dir.mkdir(parents=True, exist_ok=True)
    status_path = Path(output) / ".eval-status.json"
    _current_workers = parallel  # mutable via control commands

    def _write_status(batch_total: int, completed: int, infra_fails: int,
                      genuine_fails: int, passes: int, paused: bool):
        """Write machine-readable status for external supervisors."""
        import time as _time
        status = {
            "eval_id": eval_id,
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": _time.time() - _start_time,
            "workers": _current_workers,
            "paused": paused,
            "batch_total": batch_total,
            "completed": completed,
            "passes": passes,
            "genuine_failures": genuine_fails,
            "infra_failures": infra_fails,
            "remaining": batch_total - completed,
            "pass_rate": round(passes / max(completed - infra_fails, 1), 3),
            "infra_rate": round(infra_fails / max(completed, 1), 3),
        }
        tmp = status_path.with_suffix(f".tmp.{threading.get_ident()}")
        with open(tmp, "w") as f:
            json.dump(status, f, indent=2)
        tmp.rename(status_path)

    def _check_control() -> dict[str, str]:
        """Read and consume control commands. Returns {command: value}."""
        commands = {}
        if not control_dir.exists():
            return commands
        for p in sorted(control_dir.iterdir()):
            if p.name.startswith("."):
                continue
            val = p.read_text().strip() if p.stat().st_size > 0 else ""
            commands[p.name] = val
            p.unlink()  # consume the command
        return commands

    _start_time = __import__("time").time()
    _paused = False

    def _run_batch(batch: list, workers: int) -> list[TaskResult]:
        """Run a batch of work items and return results."""
        nonlocal budget_warned, _current_workers, _paused
        batch_results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run_single, item): item for item in batch}

            for future in as_completed(futures):
                # Check control commands between results
                for cmd, val in _check_control().items():
                    if cmd == "pause":
                        _paused = True
                        click.echo("\n  \u23f8 Paused by external supervisor")
                    elif cmd == "resume":
                        _paused = False
                        click.echo("\n  \u25b6 Resumed by external supervisor")
                    elif cmd == "set-workers":
                        try:
                            _current_workers = max(1, int(val))
                            click.echo(f"\n  \u2699 Workers set to {_current_workers} (takes effect next batch)")
                        except ValueError:
                            click.echo(f"\n  Warning: invalid set-workers value: {val}", err=True)
                    elif cmd == "skip-task":
                        # Trip circuit breaker for this task across all conditions
                        with _cb_lock:
                            _cb_tripped.add((val,))
                        click.echo(f"\n  \u23ed Skipping task {val} by external command")

                # Honor pause: spin-wait until resumed
                while _paused:
                    import time as _t
                    _t.sleep(2)
                    for cmd2, _ in _check_control().items():
                        if cmd2 == "resume":
                            _paused = False
                            click.echo("\n  \u25b6 Resumed by external supervisor")

                item = futures[future]
                _repo, _task, _cond, rep = item
                try:
                    result = future.result()
                except Exception as e:
                    # Worker crashed (e.g., cache race, OOM) — record as infra error
                    click.echo(f"  {_task.id} ({_cond.value}): CRASH - {e}", err=True)
                    result = TaskResult(
                        task_id=_task.id,
                        condition=_cond,
                        success=False,
                        test_output="",
                        wall_clock_seconds=0,
                        input_tokens=0,
                        output_tokens=0,
                        tool_calls=0,
                        lines_changed=0,
                        files_touched=[],
                        rep=rep,
                        error=f"[worker-crash] {e}"
                    )
                batch_results.append(result)
                results.append(result)  # also accumulate globally for checkpoint
                status = "PASS" if result.success else "FAIL"
                # Build the status line with error info if failed
                rep_tag = f" [rep {rep+1}/{repetitions}]" if repetitions > 1 else ""
                line = f"  {result.task_id} ({result.condition.value}){rep_tag}: {status}"
                if not result.success:
                    if result.error:
                        error_line = result.error.split('\n')[0][:80]
                        line += f" - {error_line}"
                    elif result.test_output:
                        output_lines = [l.strip() for l in result.test_output.strip().split('\n') if l.strip()]
                        if output_lines:
                            last_line = output_lines[-1][:80]
                            line += f" - {last_line}"
                click.echo(line)
                if verbose and not result.success:
                    if result.error:
                        click.echo(f"    Error: {result.error}", err=True)
                    elif result.test_output:
                        output_lines = result.test_output.strip().split('\n')
                        tail = output_lines[-10:] if len(output_lines) > 10 else output_lines
                        click.echo("    Test output (last 10 lines):", err=True)
                        for tl in tail:
                            click.echo(f"      {tl}", err=True)

                try:
                    reporter.write_trial(result)
                except Exception as e:
                    click.echo(f"  Warning: trial write failed: {e}", err=True)

                # Checkpoint every 10 results (+ first and last) to avoid O(n^2) recompilation
                is_last = len(results) >= len(work_queue)
                if len(results) == 1 or len(results) % 10 == 0 or is_last:
                    try:
                        checkpoint_path = reporter.write_checkpoint(results, eval_id, run_config=run_config)
                        if len(results) == 1:
                            click.echo(f"  Checkpoint: {checkpoint_path} (updated every 10 results)")
                    except Exception as e:
                        click.echo(f"  Warning: checkpoint write failed: {e}", err=True)

                if budget_threshold and not budget_warned and preflight_budget:
                    cumulative_tokens = sum(r.input_tokens + r.output_tokens for r in results)
                    if cumulative_tokens > budget_threshold:
                        rem_fmt = fmt_tokens(preflight_budget.get('remaining_tokens', 0))
                        cum_fmt = fmt_tokens(cumulative_tokens)
                        click.echo(f"\n\u26a0 Budget checkpoint: {cum_fmt} tokens consumed so far (est. remaining: {rem_fmt} at start)\n")
                        refresh_budget_snapshot()
                        budget_warned = True

                # Update status file for external supervisors
                n_infra = sum(1 for r in results if r.error and r.error.startswith(Reporter.INFRA_ERROR_PREFIXES))
                n_pass = sum(1 for r in results if r.success)
                n_genuine = len(results) - n_pass - n_infra
                _write_status(len(work_queue), len(results), n_infra, n_genuine, n_pass, _paused)

        return batch_results

    def _check_docker() -> bool:
        """Return True if Docker daemon is responsive."""
        import subprocess
        try:
            r = subprocess.run(["docker", "ps"], capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def _restart_docker() -> bool:
        """Attempt to restart Docker/OrbStack. Returns True if successful."""
        import subprocess, time
        click.echo("  Attempting Docker restart...")
        # Try OrbStack first (macOS), then generic docker
        for cmd in [["open", "-a", "OrbStack"], ["open", "-a", "Docker"]]:
            try:
                subprocess.run(cmd, capture_output=True, timeout=10)
            except Exception:
                continue
        # Wait for Docker to come up
        for attempt in range(12):  # up to 60s
            time.sleep(5)
            if _check_docker():
                click.echo(f"  Docker restarted successfully (waited {(attempt+1)*5}s)")
                return True
        click.echo("  Docker restart failed after 60s", err=True)
        return False

    def _cb_reset():
        """Reset circuit breaker state between supervisor rounds."""
        with _cb_lock:
            _cb_counts.clear()
            _cb_tripped.clear()

    # ── Supervisor loop ──────────────────────────────────────────────
    MAX_RETRY_ROUNDS = 2
    current_batch = work_queue

    for supervisor_round in range(1 + MAX_RETRY_ROUNDS):
        if supervisor_round > 0:
            click.echo(f"\n{'='*60}")
            click.echo(f"Supervisor retry round {supervisor_round}/{MAX_RETRY_ROUNDS}")
            click.echo(f"{'='*60}")

        batch_results = _run_batch(current_batch, _current_workers)

        # Classify failures from this batch
        infra_results = [
            r for r in batch_results
            if r.error and (
                r.error.startswith(Reporter.INFRA_ERROR_PREFIXES)
                or r.error.startswith("[circuit-breaker]")
            )
        ]

        if not infra_results:
            break  # all clean or only genuine failures

        # Build retry queue: find work items whose results were infra errors
        infra_keys = {(r.task_id, r.condition.value, r.rep) for r in infra_results}
        retry_queue = [
            item for item in current_batch
            if (item[1].id, item[2].value, item[3]) in infra_keys
        ]

        if not retry_queue or supervisor_round >= MAX_RETRY_ROUNDS:
            if retry_queue:
                click.echo(f"\n  {len(retry_queue)} infra failures remain after {MAX_RETRY_ROUNDS} retry rounds")
            break

        click.echo(f"\n  {len(infra_results)} infra failures detected, diagnosing...")

        # Remove infra results from global list — they'll be replaced by retries
        infra_remove = {(r.task_id, r.condition.value, r.rep) for r in infra_results}
        results[:] = [r for r in results if (r.task_id, r.condition.value, r.rep) not in infra_remove]

        # Diagnose and remediate
        has_docker_failures = any(
            r.error and ("[pre-validation]" in r.error or "Docker" in r.error)
            for r in infra_results
        )
        if has_docker_failures:
            if not _check_docker():
                click.echo("  Docker is down!")
                if not _restart_docker():
                    click.echo("  Cannot recover Docker — aborting retries", err=True)
                    results.extend(infra_results)  # put them back
                    break
            # Reduce parallelism to ease Docker contention
            _current_workers = max(2, _current_workers // 2)
            click.echo(f"  Reducing parallelism to {_current_workers} workers")

        # Reset circuit breaker for retry round
        _cb_reset()
        current_batch = retry_queue
        click.echo(f"  Retrying {len(retry_queue)} items...")

    # Generate reports — capture postflight budget in cli (not reporter)
    postflight_budget = get_budget_status()
    eval_results = reporter.compile_results(
        results, preflight_budget=preflight_budget, postflight_budget=postflight_budget
    )
    # Use the pre-assigned eval_id so final report matches the checkpoint lineage
    eval_results = replace(
        eval_results,
        eval_id=eval_id,
        timestamp=eval_results.timestamp,
        run_config=run_config,
    )

    # Merge with prior results if resuming.
    # Carry forward both passed pairs AND genuine failures (unless --retry-all
    # was used, in which case genuine failures were re-run and are in new results).
    if prior_data is not None:
        carry_forward = passed_pairs | (genuine_fail_pairs if not retry_all else set())
        eval_results = _merge_results(eval_results, prior_data, carry_forward)
        eval_results.summary["resumed_from"] = prior_data.get("eval_id")

    json_path = reporter.write_json(eval_results)
    md_path = reporter.write_markdown(eval_results)

    # Remove checkpoint now that final results are written
    reporter.remove_checkpoint(eval_id)

    click.echo(f"\nResults written to:")
    click.echo(f"  JSON: {json_path}")
    click.echo(f"  Markdown: {md_path}")

    # Cleanup workspaces but preserve index cache
    if not keep_workspaces and workspaces_dir.exists():
        cache_path = Path(cache_dir)
        # Move cache out, remove workspaces, move cache back
        tmp_cache = None
        if cache_path.exists() and cache_path.is_relative_to(workspaces_dir):
            tmp_cache = workspaces_dir.parent / ".index-cache-preserve"
            if tmp_cache.exists():
                shutil.rmtree(tmp_cache)
            shutil.move(str(cache_path), str(tmp_cache))
        shutil.rmtree(workspaces_dir)
        if tmp_cache and tmp_cache.exists():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_cache), str(cache_path))
        click.echo("Cleaned up workspaces")


@main.command("run-agentbench")
@click.option("--parallel", "-p", default=4, help="Number of parallel workers")
@click.option("--output", "-o", default="results", help="Output directory")
@click.option("--timeout", default=1800, help="Per-task Claude timeout in seconds")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress for each step")
@click.option("--condition", "-c", multiple=True,
              type=click.Choice([c.value for c in Condition]),
              help="Conditions to run (default: none, flat_llm, human, intent_layer)")
@click.option("--model", default="sonnet", help="Claude model to use (default: sonnet)")
@click.option("--repetitions", "-n", default=1,
              help="Number of times to repeat each instance/condition pair (default: 1)")
@click.option("--filter-repo", default=None, help="Only run instances from this repo (e.g. ansible_ansible)")
@click.option("--filter-ids", default=None, help="Comma-separated instance IDs to run")
@click.option("--resume", default=None, type=click.Path(exists=True),
              help="Prior results JSON — skip passed pairs, re-run infra errors")
@click.option("--retry-all", is_flag=True,
              help="With --resume: also retry genuine failures, not just infra errors")
@click.option("--keep-workspaces", is_flag=True, help="Don't cleanup workspaces")
@click.option("--dry-run", is_flag=True, help="Show what would run")
@click.option("--no-cache", is_flag=True, help="Disable index caching entirely")
@click.option("--cache-dir", default="workspaces/.index-cache", help="Index cache directory")
def run_agentbench(parallel, output, timeout, verbose, condition, model, repetitions,
                   filter_repo, filter_ids, resume, retry_all, keep_workspaces,
                   dry_run, no_cache, cache_dir):
    """Run AGENTbench paper instances (138 tasks from HuggingFace)."""
    import subprocess
    import time as _time

    # --- Load instances from HuggingFace ---
    filter_id_list = [s.strip() for s in filter_ids.split(",")] if filter_ids else None
    click.echo("Loading AGENTbench instances from HuggingFace...")
    instances = load_instances(filter_repo=filter_repo, filter_ids=filter_id_list)
    if not instances:
        raise click.ClickException("No instances matched filters")
    click.echo(f"Loaded {len(instances)} instances across "
               f"{len(set(i.repo for i in instances))} repos")

    # Default conditions: all four for AGENTbench
    ALL_CONDITIONS = [Condition.NONE, Condition.FLAT_LLM, Condition.HUMAN, Condition.INTENT_LAYER]
    if condition:
        conditions = [Condition(c) for c in condition]
    else:
        conditions = ALL_CONDITIONS

    # --- Build work queue ---
    work_queue: list[tuple[AgentbenchInstance, Condition, int]] = []
    for inst in instances:
        for cond in conditions:
            for rep in range(repetitions):
                work_queue.append((inst, cond, rep))

    # --- Resume filtering ---
    passed_pairs: set[tuple[str, str]] = set()
    genuine_fail_pairs: set[tuple[str, str]] = set()
    prior_data = None
    if resume:
        passed_pairs, genuine_fail_pairs, prior_data = _load_prior_results(resume)
        skip_pairs = passed_pairs.copy()
        if not retry_all:
            skip_pairs |= genuine_fail_pairs
        work_queue = [item for item in work_queue if (item[0].instance_id, item[1].value) not in skip_pairs]
        click.echo(f"Resume: {len(passed_pairs)} passed (carried forward), "
                   f"{len(genuine_fail_pairs)} genuine failures ({'retrying' if retry_all else 'skipped'}), "
                   f"{len(work_queue)} to re-run")

    if dry_run:
        click.echo("\nDry run - would execute:")
        for inst, cond, rep in work_queue:
            rep_tag = f" [rep {rep+1}]" if repetitions > 1 else ""
            click.echo(f"  - {inst.instance_id} ({cond.value}){rep_tag}")
        if not work_queue:
            click.echo("  (nothing to re-run)")
        return

    total_unique = len(set((item[0].instance_id, item[1].value) for item in work_queue))
    rep_note = f" x{repetitions} reps" if repetitions > 1 else ""
    click.echo(f"Running {total_unique} instance/condition pairs{rep_note} "
               f"({len(work_queue)} total) with {parallel} workers")

    # --- Pre-pull Docker images ---
    unique_images = sorted(set(i.docker_image for i in instances))
    click.echo(f"Pre-pulling {len(unique_images)} Docker image(s)...")
    for image in unique_images:
        for attempt in range(3):
            try:
                subprocess.run(
                    ["docker", "pull", image],
                    capture_output=True, timeout=300, check=True,
                )
                click.echo(f"  {image}: ready")
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                if attempt < 2:
                    click.echo(f"  {image}: retry {attempt+1}/3 ({e})", err=True)
                else:
                    click.echo(f"  {image}: FAILED after 3 attempts", err=True)

    # --- Create reference clones ---
    workspaces_dir = Path("workspaces")
    unique_repos = {f"https://github.com/{i.base_repo}.git" for i in instances}
    reference_clones_str = _create_reference_clones(unique_repos, workspaces_dir)
    # Convert to Path values for agentbench_runner
    reference_clones: dict[str, Path] = {
        # Key by repo slug (e.g. "ansible/ansible") not URL
        repo_url.replace("https://github.com/", "").replace(".git", ""): Path(path)
        for repo_url, path in reference_clones_str.items()
    }

    # --- Warm caches ---
    index_cache = None if no_cache else IndexCache(cache_dir)

    progress_callback = _make_progress_callback(verbose)

    # --- Circuit breaker ---
    _cb_counts: dict[tuple[str, ...], int] = {}
    _cb_tripped: set[tuple[str, ...]] = set()
    _cb_lock = threading.Lock()
    CB_THRESHOLD = 2

    def _cb_record(task_id: str, condition_val: str, error: str) -> bool:
        with _cb_lock:
            if "[pre-validation]" in error:
                key = (task_id,)
            else:
                key = (task_id, condition_val)
            _cb_counts[key] = _cb_counts.get(key, 0) + 1
            if _cb_counts[key] >= CB_THRESHOLD:
                newly = key not in _cb_tripped
                _cb_tripped.add(key)
                return newly
        return False

    def _cb_is_tripped(task_id: str, condition_val: str) -> bool:
        with _cb_lock:
            return (task_id,) in _cb_tripped or (task_id, condition_val) in _cb_tripped

    def _cb_reset():
        with _cb_lock:
            _cb_counts.clear()
            _cb_tripped.clear()

    # --- Worker function ---
    def _run_one(item: tuple[AgentbenchInstance, Condition, int]) -> TaskResult:
        inst, cond, rep = item

        if _cb_is_tripped(inst.instance_id, cond.value):
            return TaskResult(
                task_id=inst.instance_id, condition=cond, success=False,
                test_output="", wall_clock_seconds=0,
                input_tokens=0, output_tokens=0, tool_calls=0,
                lines_changed=0, files_touched=[], rep=rep,
                error="[circuit-breaker] skipped — repeated failures for this instance",
            )

        result = agentbench_run_single(
            instance=inst,
            condition=cond,
            rep=rep,
            workspaces_dir=workspaces_dir,
            reference_clones=reference_clones,
            index_cache=index_cache,
            claude_timeout=timeout,
            model=model,
            progress_callback=progress_callback,
        )

        if result.error:
            newly_tripped = _cb_record(inst.instance_id, cond.value, result.error)
            if newly_tripped:
                scope = inst.instance_id if "[pre-validation]" in result.error else f"{inst.instance_id}/{cond.value}"
                click.echo(f"  \u26a1 Circuit breaker tripped for {scope}")

        return result

    # --- Reporter + eval ID ---
    reporter = Reporter(output)
    eval_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    run_config = {
        "task_ids": sorted(set(i.instance_id for i in instances)),
        "conditions": sorted(c.value for c in conditions),
        "repetitions": repetitions,
        "timeout": timeout,
        "model": model,
        "source": "agentbench",
        "filter_repo": filter_repo,
        "filter_ids": filter_ids,
    }

    # --- Control plane ---
    control_dir = Path(output) / ".eval-control"
    control_dir.mkdir(parents=True, exist_ok=True)
    status_path = Path(output) / ".eval-status.json"
    _current_workers = parallel
    _start_time = _time.time()
    _paused = False

    def _write_status(batch_total: int, completed: int, infra_fails: int,
                      genuine_fails: int, passes: int, paused: bool):
        status = {
            "eval_id": eval_id,
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": _time.time() - _start_time,
            "workers": _current_workers,
            "paused": paused,
            "batch_total": batch_total,
            "completed": completed,
            "passes": passes,
            "genuine_failures": genuine_fails,
            "infra_failures": infra_fails,
            "remaining": batch_total - completed,
            "pass_rate": round(passes / max(completed - infra_fails, 1), 3),
            "infra_rate": round(infra_fails / max(completed, 1), 3),
        }
        tmp = status_path.with_suffix(f".tmp.{threading.get_ident()}")
        with open(tmp, "w") as f:
            json.dump(status, f, indent=2)
        tmp.rename(status_path)

    def _check_control() -> dict[str, str]:
        commands = {}
        if not control_dir.exists():
            return commands
        for p in sorted(control_dir.iterdir()):
            if p.name.startswith("."):
                continue
            val = p.read_text().strip() if p.stat().st_size > 0 else ""
            commands[p.name] = val
            p.unlink()
        return commands

    # --- Batch runner ---
    results: list[TaskResult] = []

    def _run_batch(batch: list, workers: int) -> list[TaskResult]:
        nonlocal _current_workers, _paused
        batch_results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run_one, item): item for item in batch}
            for future in as_completed(futures):
                # Check control commands
                for cmd, val in _check_control().items():
                    if cmd == "pause":
                        _paused = True
                        click.echo("\n  \u23f8 Paused by external supervisor")
                    elif cmd == "resume":
                        _paused = False
                        click.echo("\n  \u25b6 Resumed")
                    elif cmd == "set-workers":
                        try:
                            _current_workers = max(1, int(val))
                            click.echo(f"\n  \u2699 Workers set to {_current_workers} (next batch)")
                        except ValueError:
                            click.echo(f"\n  Warning: invalid set-workers value: {val}", err=True)
                    elif cmd == "skip-task":
                        with _cb_lock:
                            _cb_tripped.add((val,))
                        click.echo(f"\n  \u23ed Skipping {val}")

                while _paused:
                    _time.sleep(2)
                    for cmd2, _ in _check_control().items():
                        if cmd2 == "resume":
                            _paused = False
                            click.echo("\n  \u25b6 Resumed")

                item = futures[future]
                _inst, _cond, rep = item
                try:
                    result = future.result()
                except Exception as e:
                    click.echo(f"  {_inst.instance_id} ({_cond.value}): CRASH - {e}", err=True)
                    result = TaskResult(
                        task_id=_inst.instance_id, condition=_cond, success=False,
                        test_output="", wall_clock_seconds=0,
                        input_tokens=0, output_tokens=0, tool_calls=0,
                        lines_changed=0, files_touched=[], rep=rep,
                        error=f"[worker-crash] {e}",
                    )
                batch_results.append(result)
                results.append(result)

                status_str = "PASS" if result.success else "FAIL"
                rep_tag = f" [rep {rep+1}/{repetitions}]" if repetitions > 1 else ""
                line = f"  {result.task_id} ({result.condition.value}){rep_tag}: {status_str}"
                if not result.success:
                    if result.error:
                        first_line = result.error.split("\n")[0][:80]
                        line += f" - {first_line}"
                    elif result.test_output:
                        non_empty = [s.strip() for s in result.test_output.strip().split("\n") if s.strip()]
                        if non_empty:
                            line += f" - {non_empty[-1][:80]}"
                click.echo(line)

                try:
                    reporter.write_trial(result)
                except Exception as e:
                    click.echo(f"  Warning: trial write failed: {e}", err=True)
                # Checkpoint every 10 results (+ first and last) to avoid O(n^2) recompilation
                is_last = len(results) >= len(work_queue)
                if len(results) == 1 or len(results) % 10 == 0 or is_last:
                    try:
                        checkpoint_path = reporter.write_checkpoint(results, eval_id, run_config=run_config)
                        if len(results) == 1:
                            click.echo(f"  Checkpoint: {checkpoint_path}")
                    except Exception as e:
                        click.echo(f"  Warning: checkpoint write failed: {e}", err=True)

                n_infra = sum(1 for r in results if r.error and r.error.startswith(Reporter.INFRA_ERROR_PREFIXES))
                n_pass = sum(1 for r in results if r.success)
                n_genuine = len(results) - n_pass - n_infra
                _write_status(len(work_queue), len(results), n_infra, n_genuine, n_pass, _paused)

        return batch_results

    # --- Supervisor loop ---
    MAX_RETRY_ROUNDS = 2
    current_batch = work_queue

    for supervisor_round in range(1 + MAX_RETRY_ROUNDS):
        if supervisor_round > 0:
            click.echo(f"\n{'='*60}")
            click.echo(f"Supervisor retry round {supervisor_round}/{MAX_RETRY_ROUNDS}")
            click.echo(f"{'='*60}")

        batch_results = _run_batch(current_batch, _current_workers)

        infra_results = [
            r for r in batch_results
            if r.error and (
                r.error.startswith(Reporter.INFRA_ERROR_PREFIXES)
                or r.error.startswith("[circuit-breaker]")
            )
        ]

        if not infra_results:
            break

        infra_keys = {(r.task_id, r.condition.value, r.rep) for r in infra_results}
        retry_queue = [
            item for item in current_batch
            if (item[0].instance_id, item[1].value, item[2]) in infra_keys
        ]

        if not retry_queue or supervisor_round >= MAX_RETRY_ROUNDS:
            if retry_queue:
                click.echo(f"\n  {len(retry_queue)} infra failures remain after {MAX_RETRY_ROUNDS} retry rounds")
            break

        click.echo(f"\n  {len(infra_results)} infra failures detected, retrying...")
        infra_remove = {(r.task_id, r.condition.value, r.rep) for r in infra_results}
        results[:] = [r for r in results if (r.task_id, r.condition.value, r.rep) not in infra_remove]

        _cb_reset()
        current_batch = retry_queue

    # --- Generate reports ---
    eval_results = reporter.compile_results(results)
    eval_results = replace(
        eval_results,
        eval_id=eval_id,
        timestamp=eval_results.timestamp,
        run_config=run_config,
    )

    if prior_data is not None:
        carry_forward = passed_pairs | (genuine_fail_pairs if not retry_all else set())
        eval_results = _merge_results(eval_results, prior_data, carry_forward)
        eval_results.summary["resumed_from"] = prior_data.get("eval_id")

    json_path = reporter.write_json(eval_results)
    md_path = reporter.write_markdown(eval_results)
    reporter.remove_checkpoint(eval_id)

    click.echo(f"\nResults written to:")
    click.echo(f"  JSON: {json_path}")
    click.echo(f"  Markdown: {md_path}")

    if not keep_workspaces and workspaces_dir.exists():
        cache_path = Path(cache_dir)
        tmp_cache = None
        if cache_path.exists() and cache_path.is_relative_to(workspaces_dir):
            tmp_cache = workspaces_dir.parent / ".index-cache-preserve"
            if tmp_cache.exists():
                shutil.rmtree(tmp_cache)
            shutil.move(str(cache_path), str(tmp_cache))
        shutil.rmtree(workspaces_dir)
        if tmp_cache and tmp_cache.exists():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_cache), str(cache_path))
        click.echo("Cleaned up workspaces")


@main.command()
@click.option("--tasks", "-t", multiple=True, required=True, help="Task YAML files")
@click.option("--parallel", "-p", default=8, help="Number of parallel workers")
@click.option("--timeout", default=300, help="Pre-validation timeout in seconds (default: 300)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress")
def validate(tasks, parallel, timeout, verbose):
    """Validate task configs without spending Claude API tokens.

    For each task: clones the repo, checks out pre_fix_commit, strips context
    files, injects test from fix_commit if applicable, and runs Docker
    pre-validation. Reports which tasks pass/fail and why.

    Use this to catch bad configs before burning API budget on a full run.
    """
    # Load all tasks, deduplicating by task ID (overlapping YAML files
    # like graphiti.yaml and graphiti-signal.yaml share task IDs)
    all_tasks = []
    seen_ids: set[str] = set()
    for task_path in tasks:
        if not Path(task_path).exists():
            raise click.ClickException(f"Task file does not exist: {task_path}")
        task_file = TaskFile.from_yaml(Path(task_path))
        for task in task_file.tasks:
            if task.id in seen_ids:
                continue
            seen_ids.add(task.id)
            all_tasks.append((task_file.repo, task))

    click.echo(f"Validating {len(all_tasks)} tasks from {len(tasks)} file(s)")

    workspaces_dir = Path("workspaces")
    progress_callback = _make_progress_callback(verbose)

    # Create reference clones
    unique_repos = {repo.url for repo, _task in all_tasks}
    reference_clones = _create_reference_clones(unique_repos, workspaces_dir)

    def validate_one(item):
        repo, task = item
        runner = TaskRunner(
            repo,
            str(workspaces_dir),
            progress_callback=progress_callback,
            use_cache=False,
            reference_clone=reference_clones.get(repo.url),
            pre_validation_timeout=timeout,
        )
        workspace = runner.setup_workspace(task, Condition.NONE, rep=0)
        error = None
        test_passes_already = False
        try:
            clone_repo(repo.url, workspace, shallow=False, reference=reference_clones.get(repo.url))
            checkout_commit(workspace, task.pre_fix_commit)
            runner._strip_context_files(workspace, repo.strip_extra or None)
            if task.prompt_source == "failing_test" and task.test_file:
                runner._inject_test_from_fix(task, workspace)
            runner._pre_validate(task, workspace, task_id=task.id, condition="validate")
        except Exception as e:
            error = str(e)
            if "already passes at pre_fix_commit" in error:
                test_passes_already = True
        finally:
            if Path(workspace).exists():
                shutil.rmtree(workspace)
        return task.id, error, test_passes_already

    results = []
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(validate_one, item): item for item in all_tasks}
        for future in as_completed(futures):
            repo, task = futures[future]
            try:
                task_id, error, test_passes = future.result()
            except Exception as e:
                task_id = task.id
                error = f"[worker-crash] {e}"
                test_passes = False
            results.append((task_id, error, test_passes))
            status = "PASS" if not error else "FAIL"
            line = f"  {task_id}: {status}"
            if error:
                line += f" - {error[:100]}"
            click.echo(line)

    # Summary
    results.sort(key=lambda r: r[0])
    passed = [r for r in results if not r[1]]
    failed = [r for r in results if r[1]]
    passes_already = [r for r in results if r[2]]

    click.echo(f"\n{'='*60}")
    click.echo(f"Results: {len(passed)}/{len(results)} tasks valid")
    if passes_already:
        click.echo(f"\nTest already passes ({len(passes_already)}) — DROP these tasks:")
        for task_id, _, _ in passes_already:
            click.echo(f"  - {task_id}")
    other_failures = [r for r in failed if not r[2]]
    if other_failures:
        click.echo(f"\nOther failures ({len(other_failures)}) — FIX config or drop:")
        for task_id, error, _ in other_failures:
            click.echo(f"  - {task_id}: {error}")
    if not failed:
        click.echo("\nAll tasks valid!")


if __name__ == "__main__":
    main()
