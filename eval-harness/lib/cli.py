# lib/cli.py
from __future__ import annotations
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import click

from lib.models import TaskFile
from lib.task_runner import TaskRunner, Condition
from lib.reporter import Reporter
from lib.git_scanner import GitScanner
from lib.git_ops import clone_repo


# Thread-safe print lock for progress output
_print_lock = threading.Lock()


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
@click.option("--timeout", default=300, help="Per-task timeout in seconds")
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
def run(tasks, parallel, category, output, keep_workspaces, dry_run, timeout, verbose, clear_cache, no_cache, cache_dir, condition, model, repetitions):
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
        from lib.index_cache import IndexCache
        cache = IndexCache(cache_dir)
        cache.clear()
        click.echo(f"Cleared index cache at {cache_dir}")

    if dry_run:
        click.echo("\nDry run - would execute:")
        for repo, task in all_tasks:
            click.echo(f"  - {task.id} ({task.category})")
        if repetitions > 1:
            click.echo(f"  (x{repetitions} repetitions each)")
        return

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

    total_unique = len(all_tasks) * len(conditions)
    rep_note = f" x{repetitions} reps" if repetitions > 1 else ""
    click.echo(f"Running {total_unique} task/condition pairs{rep_note} ({len(work_queue)} total) with {parallel} workers")
    if verbose:
        click.echo("Verbose mode: showing detailed progress", err=True)

    workspaces_dir = Path("workspaces")
    results = []
    progress_callback = _make_progress_callback(verbose)

    def run_single(item):
        repo, task, condition, rep = item
        runner = TaskRunner(
            repo,
            str(workspaces_dir),
            progress_callback=progress_callback,
            cache_dir=cache_dir,
            use_cache=not no_cache
        )
        return runner.run(task, condition, model=model)

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(run_single, item): item for item in work_queue}

        for future in as_completed(futures):
            item = futures[future]
            _repo, _task, _cond, rep = item
            result = future.result()
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


if __name__ == "__main__":
    main()
