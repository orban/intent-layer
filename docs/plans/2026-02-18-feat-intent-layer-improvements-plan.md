---
title: "feat: Eval with actual Intent Layer plugin"
type: feat
date: 2026-02-18
revised: 2026-02-19
brainstorm: docs/brainstorms/2026-02-18-intent-layer-improvements-brainstorm.md
brainstorm2: docs/brainstorms/2026-02-18-eval-improvements-brainstorm.md
---

# Eval with actual Intent Layer plugin

## Overview

Test whether the Intent Layer plugin — running as it's meant to be used — helps agents fix bugs. Previous eval runs approximated the plugin with reimplemented scripts and a custom generation prompt. This plan replaces that approximation with the actual plugin: real hooks, real delivery.

The section schema rewrite (11 → 5 sections) is deferred to a follow-up PR. Test the current plugin first. If it already helps, that's a stronger result. If it doesn't, the schema rewrite has data backing it.

## Problem statement

**The eval doesn't test the actual product.** The eval harness reimplements context generation (custom `prompt_builder.py` prompt) and delivery (custom `push-on-read-hook.sh`). These approximations differ from the real plugin in section extraction, hook matcher patterns, delivery timing, and generation quality. Results about the approximation don't tell us whether the real plugin helps.

**Data quality confounds pollute signal.** 30% infra errors, `make test` causing 29pp penalty on graphiti (slow full-suite test vs targeted tests), invalid tasks, wrong test paths.

## Technical approach

Three independent PRs, then a clean eval run:

```
┌──────────────────────────────────────────────────────────────────┐
│ PR 1: Data Quality (do first)                                    │
│   graphiti.yaml, ansible.yaml ← task config fixes                │
│   eval CLAUDE.md ← strip dev commands                            │
├──────────────────────────────────────────────────────────────────┤
│ PR 2: McNemar's Test (independent)                               │
│   stats.py ← mcnemar_test()                                     │
│   reporter.py ← paired analysis in markdown                      │
├──────────────────────────────────────────────────────────────────┤
│ PR 3: Actual Plugin in Eval (the real change)                    │
│   task_runner.py ← install actual plugin hooks                   │
│   Manually generate AGENTS.md via /intent-layer, commit to cache │
├──────────────────────────────────────────────────────────────────┤
│ Clean Eval Run (after all PRs)                                   │
│   graphiti + ansible, 5 reps, 3 conditions, McNemar's analysis   │
├──────────────────────────────────────────────────────────────────┤
│ Follow-up PR (deferred): Section Schema Rewrite                  │
│   SKILL.md, section-schema.md, templates, validator, hooks       │
│   11 sections → 5 (Boundaries, Contracts, Rules, Ownership,     │
│   Downlinks) — product change, run eval again after to compare   │
└──────────────────────────────────────────────────────────────────┘
```

### PR 1: Data quality

Fixes known eval confounds. Highest value, lowest risk. Do first.

#### 1.1 Fix task configs

**File:** `eval-harness/tasks/graphiti.yaml`
- Add `--ignore=mcp_server/tests` to test_command
- Drop `preserve-all-signatures` constraint

**File:** `eval-harness/tasks/ansible.yaml`
- Drop `fix-local-connection` task (invalid — test passes at pre-fix commit)
- Fix `fix-clearlinux` test_file path (IsADirectoryError)
- Scope test_command to specific test files

#### 1.2 Strip dev commands from eval CLAUDE.md

**Files:** Eval workspace CLAUDE.md files for graphiti and ansible

Remove: `make test`, `uv sync`, `pip install -e .`
Add: "Run only the specific test file relevant to the bug"

The `make test` confound is bigger than it looks. In graphiti, `make test` runs the full suite (~60s setup). The `none` condition discovers specific test files and runs targeted tests (~15s). Removing `make test` levels the playing field for the first time.

---

### PR 2: McNemar's test

Standalone. Gives better analysis of all past and future runs.

#### 2.1 Add McNemar's test to stats.py

**File:** `eval-harness/lib/stats.py`

Add `mcnemar_test(b: int, c: int) -> dict`:
- `b` = pairs where condition A passes, B fails
- `c` = pairs where condition A fails, B passes
- Returns `{"p_value": float, "n_discordant": int, "a_wins": int, "b_wins": int}`
- Always use exact binomial test (no scipy)

```python
def mcnemar_test(b: int, c: int) -> dict:
    n = b + c
    if n == 0:
        return {"p_value": 1.0, "n_discordant": 0, "a_wins": b, "b_wins": c}

    k = max(b, c)
    p_value = 0.0
    for i in range(k, n + 1):
        p_value += math.comb(n, i) * 0.5**n
    p_value = min(p_value * 2, 1.0)  # two-sided

    return {"p_value": p_value, "n_discordant": n, "a_wins": b, "b_wins": c}
```

#### 2.2 Update reporter for paired analysis

**File:** `eval-harness/lib/reporter.py`

For each pair of conditions, count discordant (task, rep) pairs and call `mcnemar_test()`.

**Pairing strategy:** Per (task, rep) pair. Exclude pairs where either result is an infra error (wall_clock=0, tool_calls=0). Verify that `TaskResult` exposes the rep number — if not, derive it from the ordering within each (task, condition) group.

Add a paired analysis section to markdown output:

```markdown
## Paired Analysis (McNemar's Test)

| Comparison | Discordant | A wins | B wins | p-value | Sig. |
|---|---|---|---|---|---|
| flat_llm vs none | 17 | 4 | 13 | 0.049 | * |
| intent_layer vs none | 17 | 6 | 11 | 0.332 | |
```

#### 2.3 Tests

**File:** `eval-harness/tests/test_stats.py`

- `test_mcnemar_perfect_split()`: b=0, c=10 → p<0.01
- `test_mcnemar_even_split()`: b=5, c=5 → p=1.0
- `test_mcnemar_no_discordant()`: b=0, c=0 → p=1.0
- `test_mcnemar_single_pair()`: b=0, c=1 → p=1.0 (exact binomial, two-sided)

**File:** `eval-harness/tests/test_reporter.py`

- `test_mcnemar_in_summary()`: verify correct b/c counts from known results, infra errors excluded
- `test_mcnemar_markdown_output()`: paired analysis section present in markdown

---

### PR 3: Actual plugin in eval

Replace the eval's approximation with the actual plugin. This is the key change.

#### 3.1 Context generation: manual, not automated

Run `/intent-layer` manually on each eval repo (graphiti, ansible). Check the generated AGENTS.md files. Commit them to the eval cache.

**Why manual, not automated:** Running `/intent-layer` inside the eval means Claude-calling-Claude, interactive skill prompts, non-deterministic output, and 10+ minutes per repo. It's a one-time task per repo. Generating manually and caching the result is simpler, faster, and lets us verify quality before running hundreds of eval items against it.

**Cache injection:** After running `/intent-layer` on each repo, copy the generated AGENTS.md files into the eval's `cache-manifest.json`. The `/intent-layer` skill reverts files on completion; manually commit the generated files to the cache directory instead.

**Cache key:** Include a note in the cache entry about which SKILL.md version was used for generation, so we know when to regenerate.

#### 3.2 Hook installation: use actual plugin hooks

**File:** `eval-harness/lib/task_runner.py` (lines 753-773)

Replace the custom eval hook with the actual plugin hooks:

```python
if condition == Condition.INTENT_LAYER:
    plugin_root = str(Path(__file__).resolve().parents[2])
    hooks_config = {
        "hooks": {
            "PreToolUse": [{
                "matcher": "Edit|Write|NotebookEdit",
                "hooks": [{
                    "type": "command",
                    "command": f"{plugin_root}/scripts/pre-edit-check.sh",
                    "timeout": 10,
                }]
            }],
            "SessionStart": [{
                "matcher": "",
                "hooks": [{
                    "type": "command",
                    "command": f"{plugin_root}/scripts/inject-learnings.sh",
                    "timeout": 15,
                }]
            }],
        }
    }
    env["CLAUDE_PLUGIN_ROOT"] = plugin_root
```

**Environment notes:**
- `CLAUDE_PLUGIN_ROOT` lets hook scripts find `lib/common.sh`, `lib/find_covering_node.sh`, etc. Each script has a fallback using `dirname BASH_SOURCE[0]`, but setting the env var explicitly is more reliable.
- `CLAUDE_PROJECT_DIR` is set by Claude CLI to the project directory. In the eval, this will be the workspace directory. The hook scripts fall back to `.` if unset, which resolves to the workspace — correct behavior.
- The `.intent-layer/` directory won't exist in eval workspaces. `inject-learnings.sh` will silently skip pending-mistake checks (no pending dir). `pre-edit-check.sh` will silently skip the injection audit log. Both are fine.

**Matcher change:** The PreToolUse matcher changes from `Read|Grep|Edit|Write|NotebookEdit` (eval's custom hook fires on reads) to `Edit|Write|NotebookEdit` (the actual plugin fires on writes only). This is the authentic behavior — context gets injected when the agent starts editing, not when it's reading.

**SessionStart confound:** The `inject-learnings.sh` hook calls `resolve_context.sh`, which injects root-level context at session start. The current eval doesn't do this — it only has push-on-read. This means the `intent_layer` condition will get root context at start AND subsystem context on edit. This is the actual plugin behavior and should be tested as-is, but note it when comparing results to previous runs.

#### 3.3 Also pass CLAUDE_PLUGIN_ROOT to run_claude for fix phase

**File:** `eval-harness/lib/task_runner.py` (around line 786)

The `run_claude` call for the fix phase needs `extra_env={"CLAUDE_PLUGIN_ROOT": plugin_root}` so that hooks can find their dependencies at runtime:

```python
claude_result = run_claude(workspace, prompt, timeout=self.claude_timeout,
                           model=model, stderr_log=str(fix_log),
                           extra_env={"CLAUDE_PLUGIN_ROOT": plugin_root})
```

#### 3.4 Keep old code as fallback

Do NOT delete `push-on-read-hook.sh` or `build_skill_generation_prompt()` yet. Keep them until a successful eval run confirms the actual plugin hooks work. Delete in a follow-up PR.

#### 3.5 Tests

**File:** `eval-harness/tests/test_task_runner.py` or new test file

- Test that `CLAUDE_PLUGIN_ROOT` is set in env for `intent_layer` condition
- Test that hook config points to actual plugin scripts (verify paths exist on disk)
- Test that PreToolUse matcher is `Edit|Write|NotebookEdit` (not the old read-inclusive pattern)
- Test that `none` and `flat_llm` conditions do NOT set `CLAUDE_PLUGIN_ROOT` or install plugin hooks
- **Integration smoke test:** Run `pre-edit-check.sh` against a sample AGENTS.md file (with current section names: Pitfalls, Contracts, Patterns) and verify it extracts content. This catches "hook fires but returns empty" issues.

---

### Clean eval run

After all three PRs are merged.

#### Run configuration

- **Repos:** graphiti (7 tasks after fixes) + ansible (9 tasks after dropping invalid one)
- **Conditions:** none, flat_llm, intent_layer (actual plugin with PreToolUse + SessionStart hooks)
- **Reps:** 5 minimum
- **Estimated items:** 16 tasks × 3 conditions × 5 reps = 240 task runs

#### Pre-run checklist

- [ ] Task config fixes applied (PR 1)
- [ ] Dev commands stripped from eval CLAUDE.md (PR 1)
- [ ] AGENTS.md files generated via /intent-layer and committed to cache (PR 3)
- [ ] Plugin hooks fire correctly in eval workspace (PR 3, verified)
- [ ] McNemar's test in reporter output (PR 2, verified)
- [ ] Eval cache cleared for affected repos

#### Analysis plan

1. **Primary comparison:** intent_layer vs none (McNemar's, per (task, rep) pairs)
2. **Secondary comparison:** flat_llm vs none (replication check — should still show flat hurts)
3. **Per-repo breakdown:** separate McNemar's for graphiti and ansible
4. **Effect size:** report discordant pair ratio
5. **Cross-run comparison:** note that intent_layer now includes SessionStart injection (new vs previous runs)

---

### Deferred: Section schema rewrite

Separate PR after the clean eval run. This is a product change, not eval infrastructure.

**What:** Replace 11-section AGENTS.md format with 5 agent-optimized sections (Boundaries, Contracts, Rules, Ownership, Downlinks). Update SKILL.md generation prompt, section-schema.md, templates, explorer agent, validate_node.sh, pre-edit-check.sh.

**When:** After the clean eval run with the current plugin. If the current format already helps, the rewrite has a clear baseline to improve on. If it doesn't help, the rewrite addresses a known problem with data to back it.

**Files:** See brainstorm doc (`docs/brainstorms/2026-02-18-intent-layer-improvements-brainstorm.md`, lines 45-150) for the full 5-section spec and generation prompt.

**After shipping:** Regenerate AGENTS.md files for eval repos, commit to cache, re-run eval, compare to pre-rewrite results.

## Alternative approaches considered

1. **Keep eval approximation** — Rejected. Testing a reimplementation doesn't tell us whether the actual product works.

2. **Automate /intent-layer generation inside the eval harness** — Rejected. Claude-calling-Claude is fragile, non-deterministic, and slow. Manual generation + cache is simpler for a one-time-per-repo task.

3. **Rewrite section schema before eval (Phase 2 in original plan)** — Deferred. All three reviewers flagged this as a product change masquerading as eval prep. Test the current plugin first to establish a baseline.

4. **Delete old eval code immediately** — Deferred. Keep `push-on-read-hook.sh` and `build_skill_generation_prompt()` as fallback until the actual plugin hooks are validated in a successful eval run.

5. **4th condition (intent_layer_preamble)** — Rejected. Adds complexity. Test the plugin as-is first.

6. **All 5 plugin hooks in eval** — Rejected for now. PostToolUse, PostToolUseFailure, and Stop hooks capture learnings for future sessions. In a single eval run with no prior history, they add overhead without benefit.

## Acceptance criteria

### Functional requirements

- [ ] Eval installs actual plugin hooks (PreToolUse + SessionStart) for intent_layer condition
- [ ] `CLAUDE_PLUGIN_ROOT` set correctly in env for hook and fix phases
- [ ] `none` and `flat_llm` conditions have no plugin hooks
- [ ] McNemar's test results appear in eval report markdown
- [ ] AGENTS.md files generated by real /intent-layer skill are in eval cache
- [ ] Task config fixes applied (invalid tasks removed, paths fixed)

### Non-functional requirements

- [ ] Plugin hooks complete in <500ms (existing contract)
- [ ] McNemar's test uses exact binomial (no scipy dependency)
- [ ] Infra errors excluded from McNemar's pairing

### Quality gates

- [ ] `eval-harness/tests/test_stats.py` passes with McNemar's tests
- [ ] `eval-harness/tests/test_reporter.py` passes with paired analysis tests
- [ ] Integration smoke test: `pre-edit-check.sh` extracts content from current-format AGENTS.md
- [ ] At least one clean eval run completes with 3 conditions on graphiti

## Risk analysis

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Plugin hooks interfere with eval timing | Low | Medium | Hooks have 10s/15s timeouts. Monitor wall_clock for anomalies. |
| Current-format AGENTS.md content isn't useful | Medium | High | This is the thing we're testing. If results are negative, the schema rewrite (deferred PR) addresses it. |
| PreToolUse writes-only matcher misses useful read-time injection | Medium | Medium | Authentic plugin behavior. Monitor token counts to see if agent reads AGENTS.md voluntarily. |
| SessionStart hook injects setup prompt for repos without AGENTS.md | Low | Low | Only for `intent_layer` condition, which has AGENTS.md on disk. `detect_state.sh` should return partial/complete, not none. Verify in smoke test. |
| inject-learnings.sh injects root context as new confound | Medium | Low | This is authentic plugin behavior. Note in results when comparing to previous runs. |

## Files to create/modify

### PR 1 (data quality)

| File | Action | Change |
|---|---|---|
| `eval-harness/tasks/graphiti.yaml` | Modify | test_command, constraints |
| `eval-harness/tasks/ansible.yaml` | Modify | Drop task, fix paths, scope tests |
| Eval workspace CLAUDE.md files | Modify | Strip dev commands |

### PR 2 (McNemar's test)

| File | Action | Change |
|---|---|---|
| `eval-harness/lib/stats.py` | Extend | Add ~15 lines (mcnemar_test) |
| `eval-harness/lib/reporter.py` | Modify | Pairing logic + markdown section |
| `eval-harness/tests/test_stats.py` | Extend | 4 test functions |
| `eval-harness/tests/test_reporter.py` | Extend | 2 test functions |

### PR 3 (actual plugin in eval)

| File | Action | Change |
|---|---|---|
| `eval-harness/lib/task_runner.py` | Modify | Hook config → actual plugin hooks, CLAUDE_PLUGIN_ROOT in env |
| Eval cache directory | Add | Manually generated AGENTS.md files for graphiti + ansible |

## References

### Internal

- Brainstorm: `docs/brainstorms/2026-02-18-intent-layer-improvements-brainstorm.md`
- Eval improvements brainstorm: `docs/brainstorms/2026-02-18-eval-improvements-brainstorm.md`
- Plugin PreToolUse hook: `scripts/pre-edit-check.sh`
- Plugin SessionStart hook: `scripts/inject-learnings.sh`
- Plugin hook config: `hooks/hooks.json`
- Stats module: `eval-harness/lib/stats.py`
- Reporter: `eval-harness/lib/reporter.py`
- Task runner: `eval-harness/lib/task_runner.py`

### External

- AGENTbench paper: arxiv 2602.11988v1
- Paper repo: https://github.com/eth-sri/agentbench
- AGENTS.md spec: https://agents.md/
- Wilson CIs paper: Bowyer et al. 2025, arxiv 2503.01747
