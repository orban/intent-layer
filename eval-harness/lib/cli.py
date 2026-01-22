"""CLI entry point for eval-harness."""

import click


@click.group()
def main():
    """A/B evaluation framework for Claude skills."""
    pass


@main.command()
@click.option("--repo", required=True, help="Repository URL to scan")
def scan(repo: str):
    """Scan repository for evaluation tasks."""
    click.echo(f"Scanning {repo}...")


@main.command()
@click.option("--tasks", required=True, help="Path to tasks YAML file")
@click.option("--parallel", default=1, help="Number of parallel workers")
def run(tasks: str, parallel: int):
    """Run evaluation tasks."""
    click.echo(f"Running tasks from {tasks} with {parallel} workers...")


if __name__ == "__main__":
    main()
