---
title: Fix eval harness for Run 4
type: fix
date: 2026-02-18
---

# Fix eval harness for Run 4

## Overview

Run 3 (overnight 2026-02-17) exposed a measurement bug and several task config issues that wasted 36% of compute. This plan fixes the timeout classification bug, drops/fixes broken task configs, and tunes parameters for Run 4.

## Problem statement

Three categories of issues:

1. **Measurement bug**: `[timeout]` errors are classified as infrastructure errors and excluded from the success rate denominator. Runs where Claude actively worked for 300s (tool_calls > 0, meaningful token usage) are treated as if they never happened. This inflated reported rates by 8-12pp and disproportionately affected flat_llm/intent_layer (which timeout more due to context reading overhead).

2. **Broken task configs**: 6 of 27 tasks never produced valid data (5 ansible tasks with no unit tests or invalid pre_fix, 1 graphiti task with pre_fix passing). 1 ansible task had wrong test_file path (directory instead of file). graphiti's test_command was missing `--ignore=mcp_server/tests`, causing spurious collection errors.

3. **Timeout budget too tight**: 300s isn't enough for context-heavy conditions. none=11% timeout rate, flat/intent=22-23%. Context makes Claude explore more before coding, but the budget cuts it off. This is a confound — we can't distinguish "context confused the agent" from "context made the agent more thorough but it ran out of time."

## Proposed solution

Five changes, all in a single commit:

### A. Remove `[timeout]` from infra error classification

**Files**: `lib/reporter.py:258`, `lib/cli.py:23-26`

```python
# lib/reporter.py:258 — BEFORE
return r.error.startswith(("[infrastructure]", "[pre-validation]", "[skill-generation]", "[empty-run]", "[timeout]"))

# lib/reporter.py:258 — AFTER
return r.error.startswith(("[infrastructure]", "[pre-validation]", "[skill-generation]", "[empty-run]"))
```

```python
# lib/cli.py:23-26 — BEFORE
_INFRA_ERROR_PREFIXES = (
    "[infrastructure]", "[pre-validation]", "[skill-generation]",
    "[empty-run]", "[timeout]",
)

# lib/cli.py:23-26 — AFTER
_INFRA_ERROR_PREFIXES = (
    "[infrastructure]", "[pre-validation]", "[skill-generation]",
    "[empty-run]",
)
```

**Rationale**: Timeouts with agent activity are genuine experimental outcomes. The agent tried and failed to finish. Only true harness failures (setup crashes, pre-validation, empty runs with 0 tool calls) should be excluded.

**Test updates needed**:

- `tests/test_task_runner.py:741-759` — `test_timeout_tag_is_infra_error`: rename to `test_timeout_tag_is_not_infra_error`, flip assertion to `is False`
- `tests/test_task_runner.py:474-521` — `test_error_tag_classification`: add a timeout case asserting `is False`
- `tests/test_resume.py:565-569` — `test_all_infra_prefixes`: remove `"[timeout]"` from the loop
- `tests/test_resume.py:257` — comment about "timeout is infra error" needs updating, and the assertion: flat_llm_success_rate should now be 0.0 (0 successes / 1 valid) instead of 0 (excluded)
- `tests/test_reporter.py` — any tests that rely on timeouts being excluded need review

### B. Drop 5 broken ansible tasks

**File**: `tasks/ansible.yaml`

Remove these task blocks entirely:

| Task ID | Reason |
|---------|--------|
| `fix-local-connection-become-bytearray` | Test passes at pre_fix_commit (9/9 pre-validation fail) |
| `fix-iptables-match-extension-bug` | Integration tests only; ansible's custom pytest wrapper rejects `--tb=short -q` |
| `callback-filter-ansible-prefix-in-debug` | Same — integration tests only, all SystemExit |
| `action-make-tmp-path-fix-error-message` | Same — no unit test changes |
| `config-lookup-fallback-to-existing-constants` | Same — integration tests only |

Surviving ansible tasks (5): fix-clearlinux, fix-get-url-regex, fix-ansiblemodule-human-to-bytes, inventory-add-warning, fix-v1-source-info-schema-validation.

### C. Fix ansible clearlinux test_file path

**File**: `tasks/ansible.yaml`

```yaml
# BEFORE
  test_file: test/units/module_utils/facts/system/distribution/

# AFTER
  test_file: test/units/module_utils/facts/system/distribution/test_parse_distribution_file_ClearLinux.py
```

Verified against the actual ansible repo: the directory contains multiple test files, and `test_parse_distribution_file_ClearLinux.py` is the specific one exercising the ClearLinux parser. Confirmed it exists at both pre_fix (`28927a70`) and fix (`869088b9`) commits.

### D. Drop 1 broken graphiti task + fix test_command

**File**: `tasks/graphiti.yaml`

Remove `preserve-all-signatures-when-edge-type-reused` — test passes at pre_fix_commit.

Add `--ignore=mcp_server/tests` to the test_command:

```yaml
# Add this line to the --ignore list
      --ignore=mcp_server/tests
```

Without this, `mcp_server/tests` causes a `ModuleNotFoundError: No module named 'tests.conftest'` collection error that makes pytest report failure even when actual tests pass.

### E. Raise Claude timeout from 300s to 450s

**File**: `lib/cli.py` (the `--timeout` default)

```python
# BEFORE
@click.option("--timeout", default=300, help="Per-task timeout in seconds")

# AFTER
@click.option("--timeout", default=450, help="Per-task timeout in seconds")
```

**Rationale**: 300s → 450s gives context-heavy conditions 50% more time. The current 300s budget creates a confound where we can't distinguish "context hurts" from "context makes Claude more thorough but budget is too tight." 450s is a compromise — 600s would reduce throughput too much for 21 tasks x 3 conditions x 5 reps.

No code changes needed for repetitions — that's just a CLI flag (`-n 5`) at run time.

## Task census after fixes

| Repo | Before | After | Expected informative |
|------|--------|-------|---------------------|
| pdm | 7 | 7 | 4 (3 at ceiling) |
| graphiti | 10 | 9 | 6-9 |
| ansible | 10 | 5 | 3-5 |
| **Total** | **27** | **21** | **13-18** |

## Acceptance criteria

- [x] `[timeout]` errors count as genuine failures in success rate denominators
- [x] `[timeout]` errors still count as failures in ITT (intent-to-treat) rates (no change needed — ITT already counts everything)
- [x] All existing tests pass after updates (194 passed, 1 skipped)
- [x] ansible.yaml has exactly 5 tasks
- [x] graphiti.yaml has exactly 9 tasks, test_command includes `--ignore=mcp_server/tests`
- [x] `fix-clearlinux` test_file points to `.py` file, not directory
- [x] Default timeout is 450s
- [x] `--dry-run` with updated configs shows 21 tasks x 3 conditions = 63 pairs

## MVP

### Changes by file

1. `lib/reporter.py` — remove `"[timeout]"` from `_is_infra_error` tuple
2. `lib/cli.py` — remove `"[timeout]"` from `_INFRA_ERROR_PREFIXES`, change timeout default to 450
3. `tasks/ansible.yaml` — remove 5 tasks, fix clearlinux test_file
4. `tasks/graphiti.yaml` — remove 1 task, add --ignore to test_command
5. `tests/test_task_runner.py` — update timeout classification tests
6. `tests/test_resume.py` — update `[timeout]` infra error assertions
7. `tests/test_reporter.py` — review and update any timeout-dependent assertions

## Risks & edge cases

1. **Zero-tool-call timeouts**: A run that times out with `tool_calls=0` currently gets tagged `[timeout]`, not `[empty-run]`. After this change it counts as a failure. Run 3 had zero such cases (all 46 timeouts had activity), so this is theoretical. Accept for now — if it appears in Run 4, revisit.

2. **Dual infra-error implementations**: `reporter._is_infra_error` and `cli._is_infra_error_dict` must stay in sync but share no code. The `cli.py:22` comment says "shared" but they're separate tuples. Both must be updated. Future work: consolidate into one import.

3. **`--resume` from Run 3 JSON**: Run 3's multi-run `total_valid_runs` fields were computed with the old rule (timeouts excluded). `_recompute_summary` reads these values directly, so a `--resume` off Run 3 data would give inconsistent treatment. Not a blocker since Run 4 is a fresh run.

4. **Test assertion subtlety at `test_resume.py:257`**: The numeric assertion `== 0` passes whether the timeout is excluded (no valid runs → 0) or counted (0/1 → 0.0). The test won't catch a missed update. Must update the comment and verify the code path manually.

5. **Runtime estimate**: At 450s timeout with ~20% timeout rate, mean per-item is closer to 210s than 180s. Realistic estimate: ~6-6.5 hours with 3 workers, not 5.25h.

## Run 4 command

After fixes, Run 4 would be:

```bash
eval-harness run \
  --tasks tasks/pdm.yaml tasks/graphiti.yaml tasks/ansible.yaml \
  --parallel 3 \
  --repetitions 5 \
  --timeout 450 \
  -v
```

21 tasks x 3 conditions x 5 reps = 315 items. At ~3 min/item with 3 workers, estimated ~5.25 hours.

## References

- Run 3 results: `results/2026-02-18-041001.json`
- Post-mortem: conversation history from 2026-02-18 morning session
- Timeout bug: `lib/reporter.py:250-258`, `lib/cli.py:22-26`
- Test files: `tests/test_task_runner.py:741`, `tests/test_resume.py:562`
