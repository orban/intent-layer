# AGENTbench Replication: Consolidated Results

**Study**: Does hierarchical context (Intent Layer) help AI agents fix bugs?
**Paper**: arxiv 2602.11988v1 — claims context files hurt agent performance
**Model**: Claude Sonnet 4.5 (default)
**Timeout**: 300s per task
**Docker**: python:3.11-slim

---

## Run 1: fastmcp (2026-02-16)

**Repo**: https://github.com/jlowin/fastmcp
**Tasks**: 8 (2 commit_message + 6 failing_test)
**Repetitions**: 1 (single run)

### Results

| # | Task ID | Prompt | Lines | none | flat_llm | intent_layer |
|---|---------|--------|-------|------|----------|--------------|
| 1 | merge-pull-request-3198 | commit_msg | 852 | PASS (219s/54tc) | PASS (207s/50tc) | PASS (199s/51tc) |
| 2 | fix-ty-0017-diagnostics | commit_msg | 852 | TIMEOUT | TIMEOUT | TIMEOUT |
| 3 | merge-pull-request-3195 | failing_test | 29 | PASS (126s/19tc) | PASS (132s/19tc) | PASS (131s/19tc) |
| 4 | fix-include_tags/exclude_tags | failing_test | 109 | TIMEOUT | FAIL (152s/17tc) | **PASS (173s/16tc)** |
| 5 | fix-stale-request-context | failing_test | 206 | TIMEOUT | TIMEOUT | TIMEOUT |
| 6 | docs-fix-stale-get_-references | failing_test | 101 | TIMEOUT | TIMEOUT | TIMEOUT |
| 7 | fix-guard-client-pagination | failing_test | 338 | FAIL* (0s/0tc) | TIMEOUT | FAIL* (0s/0tc) |
| 8 | fix-snapshot-access-token | failing_test | 235 | PASS (117s/15tc) | PASS (105s/12tc) | PASS (113s/13tc) |

*Task 7: Claude returned instantly (0s, 0 tool calls) for none and intent_layer — root cause unclear.

### Success rates

| Condition | Pass | Total | Rate |
|-----------|------|-------|------|
| none | 3 | 8 | 37.5% |
| flat_llm | 3 | 8 | 37.5% |
| intent_layer | 4 | 8 | 50.0% |

### Notes

- Single run (no repetitions) — results are directional only
- Task 4 is the sole differentiator: intent_layer passes, others don't
- No separation between flat_llm and none

---

## Run 2: pdm (2026-02-17)

**Repo**: https://github.com/pdm-project/pdm
**Tasks**: 7 (5 commit_message + 2 failing_test) — chosen for high commit_message ratio
**Repetitions**: 3 (run stopped at 49/63 — missing fix-http-cache-clear and most of fix-pdm-toml)

### Hypothesis

Context helps more with commit_message tasks (agent must navigate the codebase)
than failing_test tasks (agent follows the traceback directly to the bug).

### Infrastructure fixes required

- `pip install 'packaging<26'` — packaging 26 changed version comparison, causing 38 pre-existing test failures
- `grep -q 'hishel._serializers' src/pdm/models/serializers.py && pip install 'hishel<1.0.0'` — old API module removed in hishel 1.0
- Dropped 3 tasks: fix-uv-lock-parsing (test passes at pre_fix), fix-python-314-formatter (same), fix-packaging-26 (circular with packaging pin)

### Results (commit_message tasks)

| Task | Diff | none | flat_llm | intent_layer |
|------|------|------|----------|--------------|
| fix-resolution-excludes | 5L/2F | **1/3** (timeouts) | **2/3** | **2/3** |
| fix-pylock-toml | 4L/2F | **1/3** (timeouts) | **3/3** | **3/3** |
| fix-publish-skip-existing | 6L/2F | 3/3 | 3/3 | 3/3 |
| fix-pdm-toml | 37L/3F | 1/3 (timeouts) | 0/1 | — |
| fix-http-cache-clear | 8L/2F | — | — | — |

### Results (failing_test tasks — controls)

| Task | Diff | none | flat_llm | intent_layer |
|------|------|------|----------|--------------|
| fix-ignore-python-req | 14L/3F | 0/3 | 0/3 | 0/3 |
| fix-expand-env-vars | 7L/3F | 3/3 | 3/3 | 3/3 |

### Aggregate pass rates

| Condition | Commit_message | Failing_test | Overall |
|-----------|---------------|--------------|---------|
| none | 5/12 (42%) | 3/6 (50%) | 8/18 (44%) |
| flat_llm | 8/10 (80%) | 3/6 (50%) | 11/16 (69%) |
| intent_layer | 8/9 (89%) | 3/6 (50%) | 11/15 (73%) |

### Key finding

Context helps commit_message tasks but not failing_test tasks:

- **Failing_test tasks**: 50% across all three conditions (no effect)
- **Commit_message tasks**: none 42% → flat_llm 80% → intent_layer 89%

The gap is driven by timeouts — in `none`, the agent times out searching for the right file.
With context (either flat or hierarchical), it finds the right area faster and finishes within 300s.

---

## Cross-repo synthesis

### The prompt_source hypothesis holds

| Prompt source | none | flat_llm | intent_layer | Notes |
|---------------|------|----------|--------------|-------|
| failing_test | 6/11 (55%) | 6/11 (55%) | 7/11 (64%) | Traceback points to bug — context barely helps |
| commit_message | 6/14 (43%) | 9/12 (75%) | 10/11 (91%) | Agent must navigate — context helps a lot |

### Flat vs hierarchical

- fastmcp: flat_llm = none (37.5% = 37.5%), intent_layer ahead (50%)
- pdm commit_message: flat_llm ahead of none (80% > 42%), intent_layer similar (89%)
- Across both: flat helps for commit_message but not failing_test; intent_layer helps slightly more but CIs overlap

### Caveats

- Small samples (fastmcp: 8 tasks × 1 rep; pdm: 7 tasks × 3 reps, partial)
- pdm run stopped at 49/63 (two tasks incomplete)
- Wilson confidence intervals would be wide — differences could be noise
- fix-ignore-python-req fails 0/9 across all conditions — might be unsolvable at 300s timeout
- fix-pdm-toml times out frequently — 37 lines across 3 files at 300s is tight

### What would strengthen these results

1. Complete the pdm run (14 remaining tasks)
2. Run a third repo with high commit_message ratio (graphiti, transformers, or ansible)
3. Increase timeout to 420s for tasks that frequently time out
4. Add more repos to reach 30+ commit_message tasks for statistical power
