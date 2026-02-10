# eval-harness

> **TL;DR**: A/B testing framework for Claude skills. Mines git history for bug-fix commits, runs Claude with/without skills, compares results.

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
└── models.py        # Pydantic models for tasks/configs
```

**Data flow**: Task YAML → clone repo → checkout pre-fix commit → docker setup → (optionally) generate Intent Layer → run Claude → run tests → report

## Contracts

- Task YAML must include `repo.url`, `repo.docker.image`, `repo.docker.test_command`
- Docker images must have test framework pre-installed or use setup commands
- Claude CLI must be installed and accessible in PATH
- Workspaces are created in `workspaces/` and cleaned up unless `--keep-workspaces`

## Pitfalls

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
