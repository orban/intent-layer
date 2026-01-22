# Eval Harness

A/B evaluation framework for Claude skills.

## Setup

```bash
cd eval-harness
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# Scan repo for tasks
eval-harness scan --repo https://github.com/example/repo

# Run eval
eval-harness run --tasks tasks/repo.yaml --parallel 4
```
