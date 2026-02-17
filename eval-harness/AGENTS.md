# eval-harness

> **TL;DR**: A/B testing framework for Claude skills. Mines git history for bug-fix commits, runs Claude with/without skills, compares results.

## Purpose

A/B testing framework for Claude skills. Mines git history for bug-fix commits, runs Claude with and without skills against the pre-fix state, compares whether the skill helps Claude fix the bug.

## Entry Points

| Task | Start Here |
|------|------------|
| Run evaluation | `eval-harness run --tasks tasks/*.yaml -v` |
| Find test cases | `eval-harness scan --repo URL --output tasks/repo.yaml` |
| Add new repo | Create YAML in `tasks/` with docker config |
| Debug failures | Check `results/` JSON/Markdown reports |

## Architecture

```
lib/
├── cli.py           # Click CLI commands (run, scan)
├── task_runner.py   # Orchestrates clone → setup → claude → test
├── claude_runner.py # Invokes Claude CLI, parses JSON output
├── docker_runner.py # Isolated test execution in containers
├── git_scanner.py   # Mines commits for bug-fix patterns
├── git_ops.py       # Clone, checkout, diff utilities
├── prompt_builder.py # Constructs prompts from commit/test/issue
├── reporter.py      # JSON/Markdown result generation
├── index_cache.py   # Caches Intent Layer generation per repo+skill hash
└── models.py        # Pydantic models for tasks/configs
```

**Data flow**: Task YAML → clone repo → checkout pre-fix commit → docker setup → check index cache → (cache miss) generate Intent Layer → run Claude → run tests → diff stats → report

## Contracts

- Task YAML must include `repo.url`, `repo.docker.image`, `repo.docker.test_command`
- Docker images must have test framework pre-installed or use setup commands
- Claude CLI must be installed and accessible in PATH
- Workspaces are created in `workspaces/` and cleaned up unless `--keep-workspaces`

## Pitfalls

### Unhandled future.result() in as_completed kills entire parallel run

A single worker crash (OOM, race condition) raises an exception from future.result() in the as_completed loop. Without try/except, this kills the entire run. Wrap in try/except and record as a [worker-crash] TaskResult so remaining tasks continue.

_Source: learn.sh | added: 2026-02-17_

### Workspace name collision when parallel tasks share the same base commit

If two tasks have the same pre_fix_commit, workspace names like {repo}-{commit[:8]}-{condition}-r{rep} collide. One task's _setup_workspace calls shutil.rmtree, destroying the other's in-progress work. Fix: include a hash of task.id in the workspace name.

_Source: learn.sh | added: 2026-02-17_

### ThreadPoolExecutor threads share PID — use thread ID for unique tmp filenames

os.getpid() is identical for all threads in a ThreadPoolExecutor. Two threads writing to the same tmp file (e.g., cache-manifest.tmp.61234) causes FileNotFoundError when one renames it before the other. Fix: append threading.get_ident() to tmp filenames.

_Source: learn.sh | added: 2026-02-17_

### Cache manifest PID fix prevents crash but not lost updates

Two concurrent workers can each load stale manifest, add their entry, and save — second save overwrites first's entry. Safe in current usage (warm_cache single-threaded, task loop sequential) but needs file locking for true parallel eval runs sharing a cache dir.

_Source: learn.sh | added: 2026-02-17_

### Multiple background task IDs can reference the same process

Background task outputs may show partial data (tail only, or just PID). Cross-reference timestamps between task outputs to confirm they're from the same run. Different task IDs can view the same process differently.

_Source: learn.sh | added: 2026-02-17_

### Empty-run detector misses Claude 0.0s instant returns

The empty-run check requires wall_clock_seconds > 1, so 0.0s returns fall through to test execution. Tests fail since no code was changed, producing misleading FAIL instead of [empty-run]. Fix: change threshold to >= 0 or check tool_calls == 0 directly.

_Source: learn.sh | added: 2026-02-17_

### Claude CLI JSON output format varies

**Problem**: `claude --output-format json` can return either:
- A **dict** with `{"usage": {...}, "tool_calls": [...]}`
- A **list** of messages `[{msg1}, {msg2}, ...]`

**Symptom**: `'list' object has no attribute 'get'` error in `parse_claude_output()`

**Solution**: Always check `isinstance(data, list)` before calling `.get()`. See `lib/claude_runner.py:parse_claude_output()` for the defensive pattern.

### Docker bind mount paths must be absolute

**Problem**: Docker `-v` flag requires absolute paths, but workspace paths may be relative.

**Solution**: Use `os.path.abspath()` before passing to docker. See `lib/docker_runner.py`.

### Index cache not invalidated when skill changes

**Problem**: Cache key includes skill hash, but changing skill files doesn't automatically clear old cache entries.

**Symptom**: Old AGENTS.md files used even after modifying `~/.claude/skills/intent-layer/`.

**Solution**: Use `--clear-cache` flag to manually clear cache after skill updates. Cache miss will regenerate with new skill version.

### Metrics structure differs with/without skill

**Problem**: `with_skill` results have nested `skill_generation` metrics, but `without_skill` does not.

**Symptom**: Accessing `result["skill_generation"]` on `without_skill` results raises KeyError.

**Solution**: Always check `if "skill_generation" in result` before accessing. See `lib/reporter.py` for the defensive pattern. Delta calculations only use top-level fix metrics, which exist in both conditions.

## Patterns

### Pre-validation test output is safely reusable for prompt building

**Preferred**: Pre-validation (step 5) runs before context file generation (step 6). Since .md files don't affect pytest results, test output from pre-validation is identical to what a fresh Docker run produces. Safe to pass cached_test_output to _build_prompt to skip redundant Docker execution.

_Source: learn.sh | added: 2026-02-17_


## Context

### AGENTbench paper has no statistical analysis — single runs, no confidence intervals

The paper (arxiv 2602.11988v1) ran each task exactly once per condition (temperature=0). No repetitions, no p-values, no confidence intervals. Their 2-4% differences are indistinguishable from noise. Our replication should use --repetitions 3-5 to measure variance, and variance itself is a signal: more context causing more variance would suggest the context is confusing the agent.

_Source: learn.sh | added: 2026-02-17_

### Targeted test files are safe for comparative eval — no evidence of collateral damage

Across all eval runs, every fix that passed the target test also passed the full test suite. Zero cases of Claude breaking unrelated tests. Running targeted tests (~15s) vs full suite (~150s) is a 10x speedup that's safe for A/B comparison, though final experiments should verify with full suite.

_Source: learn.sh | added: 2026-02-17_


## Checks

### Before Single-run eval results are not trustworthy — always use repetitions
- [ ] LLM task completion is stochastic even at temperature=0 (tool call results, timing, context window effects). A task passing in one run and failing in another is expected. Use --repetitions 3-5 minimum. Analyze: (1) majority-vote pass rate per condition, (2) variance per condition — higher variance with more context suggests the context is confusing the agent rather than helping.

_Source: learn.sh | added: 2026-02-17_

