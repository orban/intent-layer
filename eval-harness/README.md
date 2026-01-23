# Eval Harness

A/B evaluation framework for measuring Claude skill effectiveness.

## Setup

```bash
cd eval-harness
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Prerequisites

- Docker running locally
- `claude` CLI installed and configured
- Python 3.11+

## Usage

### 1. Scan a repo for bug fix tasks

```bash
eval-harness scan \
  --repo https://github.com/expressjs/express \
  --output tasks/express.yaml \
  --limit 20 \
  --docker-image node:20-slim \
  --setup "npm install" \
  --test-command "npm test"
```

Review and curate the generated `tasks/express.yaml` before running evals.

### 2. Run evals

```bash
# Run with 4 parallel workers
eval-harness run --tasks tasks/express.yaml --parallel 4

# Only simple fixes
eval-harness run --tasks tasks/express.yaml --category simple_fix

# Dry run to see what would run
eval-harness run --tasks tasks/express.yaml --dry-run

# Keep workspaces for debugging
eval-harness run --tasks tasks/express.yaml --keep-workspaces
```

### 3. View results

Results are written to `results/` as JSON and Markdown:

```bash
cat results/2026-01-21-143200.md
```

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=lib
```

## How It Works

1. **Scan**: Mine git history for bug fix commits
2. **Clone**: Create isolated workspaces per task/condition
3. **Setup**: Run Docker-based dependency installation
4. **With Skill**: Generate AGENTS.md via intent-layer skill
5. **Execute**: Run Claude to fix the bug
6. **Verify**: Run tests in Docker to check success
7. **Report**: Generate JSON + Markdown with deltas

## Metrics Captured

- Success rate (test passes)
- Wall clock time
- Input/output tokens
- Tool calls
- Lines changed
- Files touched
