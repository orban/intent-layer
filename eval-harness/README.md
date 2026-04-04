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

## Index Cache

The eval harness caches generated AGENTS.md files to avoid regenerating the Intent Layer on every run. Cache behavior:

- **Location**: `workspaces/.index-cache/`
- **Cache key**: Combination of repo name, commit SHA, and intent-layer skill hash
- **Invalidation**: Automatic when any file in `~/.claude/skills/intent-layer/` changes
- **CLI flags**:
  - `--clear-cache`: Delete all cached indexes before running
  - `--no-cache`: Disable caching entirely (always regenerate)
  - `--cache-dir PATH`: Use custom cache directory

Cache hits are reported in results with 0s indexing time.

## Metrics Structure

Results separate fix-only metrics from skill generation (indexing) metrics:

**Fix-only metrics** (used for performance comparison):
- Success rate (test passes)
- Wall clock time
- Input/output tokens
- Estimated Claude-reported USD cost for the fix pass
- Tool calls
- Lines changed
- Files touched

**Skill generation metrics** (reported separately):
- Wall clock time (indexing)
- Input/output tokens (indexing)
- Estimated Claude-reported USD cost for context generation
- Cache hit/miss status
- Files created

**Estimated cost attribution**: Reports now carry Claude's reported `total_cost_usd` end-to-end and attribute it by harness component:

- `fix_only`: the Claude edit/fix pass for the task
- `skill_generation`: the context-generation pass for `flat_llm` or `intent_layer`
- `total`: the sum of those two estimates

This is an estimate derived from Claude's own run-level USD cost reporting. It is not a per-tool or per-model pricing engine, and it currently splits cost only across harness execution components (`fix` vs `skill_generation`).

**Delta calculations**: Compare `with_skill` fix metrics vs `without_skill` metrics. Skill generation costs are visible in reports, but deltas still use fix-only metrics so the comparison stays focused on whether the added context improves bug-fixing rather than on the one-time indexing overhead.
