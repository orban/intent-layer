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
from lib.stats import wilson_score_interval, ci_overlap
from lib.git_scanner import GitScanner
from lib.git_ops import clone_repo, checkout_commit
from lib.index_cache import IndexCache


# Thread-safe print lock for progress output
_print_lock = threading.Lock()


def _load_prior_results(json_path: str) -> tuple[set[tuple[str, str]], dict]:
    """Load prior results JSON file and identify passed (task_id, condition) pairs.

    A condition is "passed" if success=True and no error field exists at the
    condition level. Works for both single-run and multi-run formats:
    - Single-run: checks top-level success + absence of error
    - Multi-run: checks aggregate success (majority pass) — individual run
      errors don't produce a top-level error field, so the check works as-is
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
    for i, task in enumerate(data["results"]):
        if not isinstance(task, dict) or "task_id" not in task:
            raise click.ClickException(
                f"Invalid results file: task at index {i} missing 'task_id' in {json_path}"
            )
        task_id = task["task_id"]
        for cond_key in ("none", "flat_llm", "intent_layer"):
            cond_data = task.get(cond_key)
            if cond_data is None:
                continue
            if cond_data.get("success") is True and "error" not in cond_data:
                passed.add((task_id, cond_key))

    return passed, data


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
        for cond_key in ("none", "flat_llm", "intent_layer"):
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

    Mirrors Reporter._compute_summary: success rates, Wilson Score CIs
    for multi-run data, and significance flags via CI overlap.
    """
    cond_stats: dict[str, dict] = {
        "none": {"successes": 0, "total": 0, "assigned": 0},
        "flat_llm": {"successes": 0, "total": 0, "assigned": 0},
        "intent_layer": {"successes": 0, "total": 0, "assigned": 0},
    }
    infra_errors = 0
    has_multi_run = False

    for task in merged_results:
        for cond_key in ("none", "flat_llm", "intent_layer"):
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
        "none_success_rate": rate(cond_stats["none"]),
        "flat_llm_success_rate": rate(cond_stats["flat_llm"]),
        "intent_layer_success_rate": rate(cond_stats["intent_layer"]),
        "none_itt_rate": itt_rate(cond_stats["none"]),
        "flat_llm_itt_rate": itt_rate(cond_stats["flat_llm"]),
        "intent_layer_itt_rate": itt_rate(cond_stats["intent_layer"]),
        "resumed_from": None,  # Filled in by caller
    }

    # Add Wilson Score CIs when multi-run data is present
    if has_multi_run:
        for label in ("none", "flat_llm", "intent_layer"):
            stats = cond_stats[label]
            if stats["total"] > 0:
                ci_lower, ci_upper, _ = wilson_score_interval(
                    stats["successes"], stats["total"], 0.90
                )
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
        for cond_key in ("none", "flat_llm", "intent_layer"):
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
@click.option("--parallel", "-p", default=2, help="Number of parallel workers")
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
              type=click.Choice(["none", "flat_llm", "intent_layer"]),
              help="Conditions to run (default: all three)")
@click.option("--model", default=None,
              help="Claude model to use (e.g., claude-sonnet-4-5-20250929)")
@click.option("--repetitions", "-n", default=1,
              help="Number of times to repeat each task/condition pair (default: 1)")
@click.option("--resume", default=None, type=click.Path(exists=True),
              help="Prior results JSON — skip passed pairs, re-run failures")
def run(tasks, parallel, category, output, keep_workspaces, dry_run, timeout, verbose, clear_cache, no_cache, cache_dir, condition, model, repetitions, resume):
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

    # Determine conditions to run
    if condition:
        conditions = [Condition(c) for c in condition]
    else:
        conditions = list(Condition)

    # Build work queue (with repetitions)
    work_queue = []
    for repo, task in all_tasks:
        for cond in conditions:
            for rep in range(repetitions):
                work_queue.append((repo, task, cond, rep))

    # Filter out passed pairs from prior run
    passed_pairs = set()
    prior_data = None
    pre_validated_tasks: frozenset[str] = frozenset()
    if resume:
        passed_pairs, prior_data = _load_prior_results(resume)
        pre_validated_tasks = _load_pre_validated_tasks(prior_data)
        original_len = len(work_queue)
        work_queue = [item for item in work_queue if (item[1].id, item[2].value) not in passed_pairs]
        click.echo(f"Resume: {len(passed_pairs)} passed pairs carried forward, {len(work_queue)}/{original_len} to re-run")
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

    workspaces_dir = Path("workspaces")
    results = []
    progress_callback = _make_progress_callback(verbose)

    # Phase 0: Create reference clones — one full network clone per unique repo.
    # Subsequent clones (warmup + task runs) use --local hardlinks from here,
    # turning ~5-10s network clones into <1s local copies.
    reference_clones: dict[str, str] = {}
    reference_dir = workspaces_dir / ".references"
    unique_repos = {repo.url for repo, _task in all_tasks}
    for repo_url in unique_repos:
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        ref_path = reference_dir / repo_name
        if not ref_path.exists():
            click.echo(f"Creating reference clone for {repo_name}...")
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            clone_repo(repo_url, str(ref_path), shallow=False)
        reference_clones[repo_url] = str(ref_path)

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

    def run_single(item):
        repo, task, condition, rep = item
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
        return runner.run(task, condition, model=model, rep=rep)

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(run_single, item): item for item in work_queue}

        for future in as_completed(futures):
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
                    error=f"[worker-crash] {e}"
                )
            results.append(result)
            status = "PASS" if result.success else "FAIL"
            # Build the status line with error info if failed
            rep_tag = f" [rep {rep+1}/{repetitions}]" if repetitions > 1 else ""
            line = f"  {result.task_id} ({result.condition.value}){rep_tag}: {status}"
            if not result.success:
                if result.error:
                    # Exception during execution - show first line
                    error_line = result.error.split('\n')[0][:80]
                    line += f" - {error_line}"
                elif result.test_output:
                    # Tests failed - extract last meaningful line from output
                    output_lines = [l.strip() for l in result.test_output.strip().split('\n') if l.strip()]
                    if output_lines:
                        last_line = output_lines[-1][:80]
                        line += f" - {last_line}"
            click.echo(line)
            # In verbose mode, show more error context for failures
            if verbose and not result.success:
                if result.error:
                    click.echo(f"    Error: {result.error}", err=True)
                elif result.test_output:
                    # Show last 10 lines of test output
                    output_lines = result.test_output.strip().split('\n')
                    tail = output_lines[-10:] if len(output_lines) > 10 else output_lines
                    click.echo("    Test output (last 10 lines):", err=True)
                    for l in tail:
                        click.echo(f"      {l}", err=True)

    # Generate reports
    reporter = Reporter(output)
    eval_results = reporter.compile_results(results)

    # Merge with prior results if resuming
    if prior_data is not None:
        eval_results = _merge_results(eval_results, prior_data, passed_pairs)
        eval_results.summary["resumed_from"] = prior_data.get("eval_id")

    json_path = reporter.write_json(eval_results)
    md_path = reporter.write_markdown(eval_results)

    click.echo(f"\nResults written to:")
    click.echo(f"  JSON: {json_path}")
    click.echo(f"  Markdown: {md_path}")

    # Cleanup workspaces but preserve index cache
    if not keep_workspaces and workspaces_dir.exists():
        import shutil
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


@main.command()
@click.option("--tasks", "-t", multiple=True, required=True, help="Task YAML files")
@click.option("--parallel", "-p", default=2, help="Number of parallel workers")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress")
def validate(tasks, parallel, verbose):
    """Validate task configs without spending Claude API tokens.

    For each task: clones the repo, checks out pre_fix_commit, strips context
    files, injects test from fix_commit if applicable, and runs Docker
    pre-validation. Reports which tasks pass/fail and why.

    Use this to catch bad configs before burning API budget on a full run.
    """
    # Load all tasks
    all_tasks = []
    for task_path in tasks:
        if not Path(task_path).exists():
            raise click.ClickException(f"Task file does not exist: {task_path}")
        task_file = TaskFile.from_yaml(Path(task_path))
        for task in task_file.tasks:
            all_tasks.append((task_file.repo, task))

    click.echo(f"Validating {len(all_tasks)} tasks from {len(tasks)} file(s)")

    workspaces_dir = Path("workspaces")
    progress_callback = _make_progress_callback(verbose)

    # Create reference clones
    reference_clones: dict[str, str] = {}
    reference_dir = workspaces_dir / ".references"
    unique_repos = {repo.url for repo, _task in all_tasks}
    for repo_url in unique_repos:
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        ref_path = reference_dir / repo_name
        if not ref_path.exists():
            click.echo(f"Creating reference clone for {repo_name}...")
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            clone_repo(repo_url, str(ref_path), shallow=False)
        reference_clones[repo_url] = str(ref_path)

    def validate_one(item):
        repo, task = item
        runner = TaskRunner(
            repo,
            str(workspaces_dir),
            progress_callback=progress_callback,
            use_cache=False,
            reference_clone=reference_clones.get(repo.url),
        )
        workspace = runner._setup_workspace(task, Condition.NONE, rep=0)
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
