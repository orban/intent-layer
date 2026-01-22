# lib/cli.py
from __future__ import annotations
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from lib.models import TaskFile
from lib.task_runner import TaskRunner, Condition
from lib.reporter import Reporter
from lib.git_scanner import GitScanner
from lib.git_ops import clone_repo


@click.group()
def main():
    """A/B eval harness for Claude skills."""
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
def run(tasks, parallel, category, output, keep_workspaces, dry_run, timeout):
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

    if dry_run:
        click.echo("\nDry run - would execute:")
        for repo, task in all_tasks:
            click.echo(f"  - {task.id} ({task.category})")
        return

    # Build work queue
    work_queue = []
    for repo, task in all_tasks:
        work_queue.append((repo, task, Condition.WITHOUT_SKILL))
        work_queue.append((repo, task, Condition.WITH_SKILL))

    click.echo(f"Running {len(work_queue)} task/condition pairs with {parallel} workers")

    workspaces_dir = Path("workspaces")
    results = []

    def run_single(item):
        repo, task, condition = item
        runner = TaskRunner(repo, str(workspaces_dir))
        return runner.run(task, condition)

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {executor.submit(run_single, item): item for item in work_queue}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "PASS" if result.success else "FAIL"
            click.echo(f"  {result.task_id} ({result.condition.value}): {status}")

    # Generate reports
    reporter = Reporter(output)
    eval_results = reporter.compile_results(results)

    json_path = reporter.write_json(eval_results)
    md_path = reporter.write_markdown(eval_results)

    click.echo(f"\nResults written to:")
    click.echo(f"  JSON: {json_path}")
    click.echo(f"  Markdown: {md_path}")

    # Cleanup
    if not keep_workspaces and workspaces_dir.exists():
        import shutil
        shutil.rmtree(workspaces_dir)
        click.echo("Cleaned up workspaces")


if __name__ == "__main__":
    main()
