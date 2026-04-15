---
title: "feat: AGENTbench native adapter for 138-instance replication"
type: feat
date: 2026-02-24
revised: 2026-02-24
brainstorm: ../brainstorms/2026-02-24-agentbench-adapter-brainstorm.md
---

# feat: AGENTbench native adapter for 138-instance replication

## Overview

Build a native adapter that loads the AGENTbench paper's 138 instances from
HuggingFace (`eth-sri/agentbench`) and runs them through our eval harness
with 4 conditions (none, flat_llm, human, intent_layer). Uses their exact
test infrastructure but our resilience and statistics pipeline.

Goal: produce a publication-quality response to the paper's claim that
context files hurt coding agent performance. Our thesis: flat context can
hurt, but hierarchical context is neutral to helpful.

## Problem statement

Our current eval runs use hand-curated YAML task files for 3-4 repos. The
paper tested 138 instances across 12 repos. To make a credible counter-claim
we must run the *same tasks* with the *same evaluation criteria* and *better
statistics*.

The paper ran n=1 at temp=0 with no confidence intervals. A 2-4% aggregate
difference could easily be noise. Our replication adds:
- A 4th condition (hierarchical context) they didn't test
- Multiple reps with Wilson CIs and paired tests (Phase 2)
- Per-task Fisher analysis to find where context actually matters (Phase 2)

## Architectural constraint: CC-in-CC

We run Claude Code CLI inside Claude Code, piggybacking on the subscription.
No direct API calls. Claude gets a prompt and works autonomously in a
Docker-mounted workspace. This means:

- We can't replicate their exact agent loop (they use direct API + custom tool calling)
- We give Claude their `problem_description` as a prompt and let it work
- This is more realistic (tests what a developer would actually do) but
  our `none` baseline won't be byte-identical to theirs
- Their published numbers are a reference point, not a target to match exactly

## Dataset schema (from HuggingFace inspection)

Each of the 138 instances has:

```
instance_id:          "ansible_ansible-83217"
repo:                 "ansible_ansible"
base_repo:            "ansible/ansible"
base_sha:             "fb7fd51b..."
docker_image:         "tgloaguen/planbenchx86_ansible_ansible:latest"
problem_description:  markdown description of the bug
setup_commands:       ["python3 -m venv .venv", "pip install -e .", ...]
test_file_names:      ["test/units/modules/test_debconf_empty_password.py"]
test_file_contents:   ["# test source code..."]
test_commands:        ["python run_pr_tests.py"]
test_file_runner:     "#!/usr/bin/env python3\n..."  # writes pr_test_results.json
repo_test_runner:     "#!/usr/bin/env python3\n..."  # writes test_results.json
repo_test_commands:   ["source .venv/bin/activate", "python run_tests.py test/units"]
repo_test_after_pr_patch: '{"test/foo.py::test_bar": true, ...}'  # JSON string
clean_pr_patch:       "diff --git a/..."  # the actual fix (for reference only)
```

Test runner output format (both runners):
```json
{"test/path/test_foo.py::test_bar": true, "test/path/test_baz.py::test_qux": false}
```
Dict of `node_id -> passed`. Both runners write JSON to workspace root
(`pr_test_results.json` and `test_results.json`).

12 unique Docker images (one per repo), all x86: `tgloaguen/planbenchx86_*`.

## Proposed solution

Three new files + modifications to three existing files. All AGENTbench-specific
code stays self-contained. The existing harness is touched minimally.

### Design principles (from review)

1. **Keep AGENTbench code contained** -- don't scatter across models.py,
   prompt_builder.py, task_runner.py. New code goes in new files.
2. **Reuse existing `TaskResult`** -- encode two-tier results in `success` +
   `test_output`, not new dataclass fields. Use `error` prefix for partial
   failures.
3. **Make reporter condition-agnostic** -- iterate over whatever conditions
   appear in results, not hardcoded lists. Adding HUMAN should be a 1-line
   enum change, not a 17-location edit.
4. **Extract supervisor loop** -- both `run` and `run-agentbench` call the
   same `_run_supervisor()`, avoiding 400 lines of duplication.
5. **No stats machinery for Phase 1** -- McNemar and Fisher are meaningless
   at n=1. Defer to Phase 2 when we have reps.

## Implementation

### Phase A: Get one instance running end-to-end

#### A1. Create `lib/agentbench_loader.py` (~50 lines)

```python
@dataclass(frozen=True)
class AgentbenchInstance:
    instance_id: str
    repo: str                    # "ansible_ansible"
    base_repo: str               # "ansible/ansible"
    base_sha: str
    docker_image: str
    problem_description: str
    setup_commands: list[str]
    test_files: list[tuple[str, str]]  # (path, content) pairs — zipped on load
    test_commands: list[str]
    test_file_runner: str
    repo_test_runner: str
    repo_test_commands: list[str]
    repo_test_after_pr_patch: dict[str, bool]
    clean_pr_patch: str | None = None


def load_instances(
    filter_repo: str | None = None,
    filter_ids: list[str] | None = None,
) -> list[AgentbenchInstance]:
    """Load from HuggingFace, zip test_file_names+contents, parse JSON fields."""
```

Key details:
- `test_file_names` and `test_file_contents` are zipped into `test_files`
  on load, making the coupling structural (not parallel arrays)
- `repo_test_after_pr_patch` is parsed from JSON string to dict on load
- Validates `len(test_file_names) == len(test_file_contents)` on load
- Frozen because instances are immutable; multiple workers share them

#### A2. Create `lib/agentbench_runner.py` (~150 lines)

Single file containing all AGENTbench-specific execution logic:

```python
def strip_agentbench_docs(workspace: Path) -> None:
    """Delete ALL .md files, .github/, docs/, .claude/, .cursor/, .codex/."""

def inject_human_context(workspace: Path, repo_url: str, default_branch: str) -> list[str]:
    """Fetch developer context files from repo HEAD. Returns list of files injected."""

def write_test_infrastructure(workspace: Path, instance: AgentbenchInstance) -> None:
    """Write test_files, test_file_runner, repo_test_runner to workspace."""

def evaluate_instance(
    workspace: Path,
    instance: AgentbenchInstance,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Two-tier evaluation. Returns (success, test_output_summary).

    Runs instance tests (test_file_runner -> pr_test_results.json)
    then regression tests (repo_test_runner -> test_results.json).
    Both must pass for success=True.

    test_output_summary is a human-readable string like:
    "INSTANCE: 3/3 passed | REGRESSION: 45/47 passed (2 flipped: test_foo, test_bar)"
    """

def build_prompt(
    problem_description: str,
    condition: Condition,
    test_output: str | None = None,
) -> str:
    """Preamble + problem_description + optional failing test output.

    Preamble: none=nothing, flat_llm/human=FLAT_PREAMBLE,
    intent_layer=INTENT_LAYER_PREAMBLE (from existing prompt_builder.py).
    """

def run_single(
    instance: AgentbenchInstance,
    condition: Condition,
    rep: int,
    workspaces_dir: Path,
    reference_clones: dict[str, Path],
    index_cache: IndexCache,
    claude_timeout: int = 1800,
    model: str = "sonnet",
) -> TaskResult:
    """Full per-instance execution. Returns a standard TaskResult.

    Steps:
    1. Clone repo at base_sha (from reference clone, hardlink)
    2. strip_agentbench_docs()
    3. Inject condition context:
       - none: nothing
       - flat_llm: generate via existing _generate_flat_context() + paper's prompt
       - human: inject_human_context() from repo HEAD
       - intent_layer: restore from IndexCache + inject hooks
    4. write_test_infrastructure()
    5. Pre-validate: instance tests should fail, regression tests should pass
    6. Create baseline commit
    7. build_prompt()
    8. run_claude()
    9. evaluate_instance()
    10. Return TaskResult(success=..., test_output=..., ...)
    """
```

Key details:
- `evaluate_instance()` returns `(bool, str)` — drops into existing
  `TaskResult.success` and `TaskResult.test_output`. No new dataclass.
- Uses `_parse_test_results()` helper that handles missing/corrupt JSON
  defensively (returns None on failure, treated as test failure).
- Timeout is split as a deadline: `end_time = time.time() + timeout`,
  remaining time passed to each Docker step.
- Reuses `run_in_docker`, `run_claude`, `clone_repo` from existing harness.
- Human preamble reuses existing `INTENT_LAYER_PREAMBLE` (tells Claude to
  look for CLAUDE.md and AGENTS.md — harmless if some don't exist).
- Flat_llm always generates fresh via existing `_generate_flat_context()`
  using the paper's prompt. No `extracted_plans.json` loader (we're already
  diverging from their exact methodology with CC-in-CC).

#### A3. Add HUMAN to Condition enum

One-line change in `lib/task_runner.py`:

```python
class Condition(Enum):
    NONE = "none"
    FLAT_LLM = "flat_llm"
    INTENT_LAYER = "intent_layer"
    HUMAN = "human"
```

The existing YAML-based `run` command never produces `HUMAN` work items,
so the existing if/elif chains in `task_runner.py` don't need HUMAN branches.
HUMAN is only used by `agentbench_runner.run_single()`.

#### A4. Refactor `lib/reporter.py` to be condition-agnostic

Replace all hardcoded condition iteration with dynamic discovery:

```python
# Before (17 locations like this):
none_runs = conditions.get("none", [])
flat_runs = conditions.get("flat_llm", [])
il_runs = conditions.get("intent_layer", [])

# After:
conditions_present = sorted(set(r.condition for r in results), key=lambda c: c.value)
baseline = Condition.NONE
treatments = [c for c in conditions_present if c != baseline]
```

McNemar and Fisher comparison pairs: generate from all unique condition
pairs dynamically, not hardcoded. Same for markdown output sections.

This is a preparatory refactor that makes adding any future condition
zero-cost. Do it first, then HUMAN "just works."

Also fix the same hardcoded lists in `cli.py`:
- `_merge_results()` (line 149): iterate conditions dynamically
- `_recompute_summary()` (line 192): same
- Choice lists in CLI flags

#### A5. Extract `_run_supervisor()` from `cli.py`

Extract the supervisor loop (work queue, ThreadPoolExecutor, circuit breaker,
control plane, retry, checkpoint, budget tracking) into a reusable function:

```python
def _run_supervisor(
    work_queue: list[WorkItem],
    run_single_fn: Callable[[WorkItem], TaskResult],
    reporter: Reporter,
    eval_id: str,
    run_config: dict,
    parallel: int = 4,
    max_retry_rounds: int = 2,
) -> list[TaskResult]:
    """Shared supervisor loop for both YAML and AGENTbench runs."""
```

Both `run` and `run-agentbench` call this. Avoids duplicating ~400 lines.

#### A6. Add `run-agentbench` subcommand to `cli.py` (~100 lines)

```
eval-harness run-agentbench \
  --conditions none flat_llm human intent_layer \
  --repetitions 1 \
  --parallel 4 \
  --timeout 1800 \
  --filter-repo ansible_ansible \
  --filter-ids "ansible_ansible-83217,getzep_graphiti-761" \
  --resume results/in-progress-*.json \
  --temperature 0
```

The subcommand:
1. Loads instances from HuggingFace (with optional filters)
2. Pre-pulls Docker images (12 unique, with retries)
3. Creates reference clones (one per repo)
4. Warms caches (intent_layer per repo, human context per repo)
5. Builds work queue: instances x conditions x reps
6. Calls `_run_supervisor()` with `agentbench_runner.run_single` as the
   run function
7. Results flow through existing reporter

#### A7. Smoke test

Pick `ansible_ansible-83217` (the first instance). Run 1 rep x 1 condition
(none). Validate:
- Docker image pulls on x86
- Clone at base_sha works
- Doc stripping runs
- Test runners write parseable JSON
- Pre-validation works (instance tests fail, regression passes)
- `run_claude()` invocation works
- Result flows through reporter

Then expand: 1 instance x 4 conditions, then 5 instances x 4 conditions.

### Phase B: Run the full 552

#### B1. Full execution

138 instances x 4 conditions x 1 rep = 552 runs at temp=0.
Run on x86 EC2 with monitor supervising.
Expected: ~16-24 hours, ~$830 Claude costs, ~$4 EC2 costs.

#### B2. Analysis

After Phase B1:
- Compare our `none` baseline to their published Claude numbers (calibration)
- Identify instances where conditions diverge
- Produce pass-rate table (the Phase 1 deliverable)

#### B3. Phase 2 decision

Based on Phase B1 results:
- Which instances warrant 3-5 rep deep-dive?
- Run Phase 2 on signal instances with full stats (McNemar, Fisher)
- Generate the publication-quality report

## File change summary

| File | Action | ~Lines | What |
|------|--------|--------|------|
| `lib/agentbench_loader.py` | **Create** | 50 | Dataclass + HuggingFace loader |
| `lib/agentbench_runner.py` | **Create** | 150 | Strip, inject, evaluate, prompt, run_single |
| `lib/cli.py` | Modify | +100, ~50 refactored | Extract `_run_supervisor()`, add `run-agentbench` |
| `lib/task_runner.py` | Modify | +1 | Add `HUMAN = "human"` to Condition enum |
| `lib/reporter.py` | Modify | ~0 net (refactor) | Make condition iteration dynamic |
| `tests/test_agentbench.py` | **Create** | 100 | Loader parsing, evaluator with mock Docker |
| **Total** | | ~400 new + ~50 refactored | |

## What was cut (and why)

| From original plan | Why cut |
|---|---|
| `AgentbenchTestResult` dataclass | Encode in existing `TaskResult.success` + `test_output` |
| `regression_delta` tracking | YAGNI — investigate manually if needed |
| New fields on `TaskResult` | Don't pollute shared type with adapter-specific fields |
| `HUMAN_PREAMBLE` constant | Reuse existing `INTENT_LAYER_PREAMBLE` |
| `build_agentbench_prompt()` in prompt_builder.py | Keep in agentbench_runner.py |
| `_strip_agentbench_docs()` on TaskRunner | Standalone function in agentbench_runner.py |
| `extracted_plans.json` cache loader | Just use existing `_generate_flat_context()` |
| 6-pair McNemar/Fisher for Phase 1 | Meaningless at n=1. Defer to Phase 2 |
| Regression Analysis markdown section | YAGNI — post-hoc script if needed |
| Separate test files per module | One test file is enough |
| 6-phase decomposition | Collapsed to 2 phases: one instance, then all 552 |

## Error handling

| Failure mode | Handling |
|---|---|
| Test runner JSON missing/corrupt | `_parse_test_results()` returns None, treated as failure |
| Docker image pull failure | Pre-pull with retries in warmup phase |
| Instance tests pass at base_sha | Pre-validation catches, recorded as `[pre-validation]` |
| Regression tests fail at base_sha | Pre-validation catches, recorded as `[pre-validation]` |
| Claude times out | Existing timeout handling, recorded as `[timeout]` |
| Instance tests pass but regression fails | `success=False`, details in `test_output` |
| Timeout cascading (two Docker steps) | Use deadline: `end_time = time.time() + timeout` |
| Worker crash | Existing try/except in supervisor, `[worker-crash]` error |

## Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Docker images stale/broken | Blocks all runs for that repo | Fallback: rebuild from setup_commands on base image |
| HuggingFace dataset schema changes | Loader breaks | Pin dataset version, validate schema on load |
| x86 emulation on ARM dev machines | Can't test locally | EC2 for execution; unit tests mock Docker |
| CC-in-CC baseline doesn't match paper | Results not directly comparable | Report as "CC-in-CC replication" not "exact replication" |
| Budget overrun | >$1500 | Circuit breaker, monitor, --filter-repo for partial runs |
| Some repos have no developer context files | `human` = `none` for those repos | Record and report; still valid data point |

## Success criteria

- [ ] Smoke test: 1 instance x 4 conditions passes end-to-end on x86
- [ ] Phase B1: >=120/138 instances complete (<=13% infra failure rate)
- [ ] Our `none` baseline within 10pp of their published Claude numbers
- [ ] Pass-rate table clearly shows per-condition results across 12 repos
- [ ] Results reproducible: same dataset, same conditions, same output format

## Dependencies

- `datasets` Python package (for HuggingFace loading)
- x86 Docker host (EC2 c5.xlarge or similar)
- AGENTbench Docker images accessible (`tgloaguen/planbenchx86_*`)
- Claude Code CLI installed and authenticated on EC2

## References

- Brainstorm: `docs/brainstorms/2026-02-24-agentbench-adapter-brainstorm.md`
- Prior plan: `docs/plans/2026-02-16-feat-agentbench-replication-three-condition-eval-plan.md`
- Paper: arxiv 2602.11988v1
- Dataset: `eth-sri/agentbench` on HuggingFace (138 instances, 12 repos)
- Paper repo: `github.com/eth-sri/agentbench`
- Existing harness: `lib/task_runner.py`, `lib/cli.py`, `lib/reporter.py`
