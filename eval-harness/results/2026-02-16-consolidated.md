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

## Run 3: Multi-repo (2026-02-17/18 overnight)

**Repos**: pdm (7 tasks) + graphiti (10 tasks) + ansible (10 tasks) = 27 tasks
**Repetitions**: 3
**Total items**: 243 (27 × 3 × 3)
**Runtime**: ~6 hours (10:07 PM → 4:10 AM)
**Infrastructure errors**: 73 (30% of items)

### Overall results

| Condition | Success rate | 90% CI |
|-----------|-------------|--------|
| none | 63% | [53%, 73%] |
| flat_llm | 57% | [46%, 68%] |
| intent_layer | **66%** | [55%, 76%] |

CIs overlap — not statistically significant at the aggregate level.

### Per-repo results

| Repo | none | flat_llm | intent_layer | Notes |
|------|------|----------|--------------|-------|
| pdm (7 tasks) | 17/21 (81%) | 14/21 (67%) | 12/21 (57%) | Context hurts — pdm tasks are simple enough that any context is distraction |
| graphiti (10 tasks) | 16/30 (53%) | 9/30 (30%) | 12/30 (40%) | Flat context actively harmful; intent_layer mitigates damage |
| ansible (10 tasks) | 10/30 (33%) | 11/30 (37%) | 12/24 (50%) | Intent_layer best; one significant result (human-to-bytes) |

### Graphiti (excluding broken tasks)

4 graphiti tasks were broken (pre-validation invalid, mcp_server/tests collection error). Excluding those:

| Condition | Valid tasks | Rate |
|-----------|------------|------|
| none | 16/18 | 89% |
| flat_llm | 9/18 | 50% |
| intent_layer | 12/18 | 67% |

Flat context dropped performance by 39 percentage points. Intent_layer recovered 17pp of that.

### Star result: fix-ansiblemodule-human-to-bytes

The only statistically significant individual result:

| Condition | Result |
|-----------|--------|
| none | 0/3 (0%) |
| flat_llm | 1/3 (33%) |
| intent_layer | **3/3 (100%)** — significant |

This is a `module_utils` bug. The hierarchical AGENTS.md at `lib/ansible/modules/` documented the module isolation boundary (modules can ONLY import from module_utils). Without this, the agent couldn't locate the right code. With it, the agent went straight to the bug.

### Flat context hurting on graphiti

Two graphiti tasks where flat_llm scored 0/3 while none scored 3/3:
- `fix-entity-extraction-adaptive-chunking`: none 3/3, flat 0/3, intent 2/3
- `fix-datetime-comparison-normalize-utc`: none 3/3, flat 0/3, intent 1/3

Root cause: the flat CLAUDE.md for graphiti was large and unfocused. Claude spent time parsing irrelevant context and timed out before fixing the code. The hierarchical AGENTS.md pointed directly to relevant subsystems (search/, driver/, llm_client/), saving orientation time.

### Data quality issues

73 infrastructure errors (30%) severely reduced statistical power:

| Issue | Tasks affected | Items lost |
|-------|---------------|------------|
| mcp_server/tests collection error (graphiti) | fix-limited-number-of-edges, sanitize-pipe-slash, escape-group-ids | 27 |
| Test passes at pre_fix_commit (invalid task) | preserve-all-signatures (graphiti), fix-local-connection (ansible) | 18 |
| IsADirectoryError (test_file is directory) | fix-clearlinux-gentoo (ansible) | 9 |
| SystemExit (no unit tests, broad pytest) | fix-iptables, callback-filter, action-make-tmp-path, config-lookup | ~18 valid but unsolvable |

Fixes for next run:
1. Add `--ignore=mcp_server/tests` to graphiti test_command
2. Drop tasks where test passes at pre_fix_commit
3. Fix test_file directory paths in harness
4. Scope ansible test_command to specific test files, or drop commit_message tasks with no unit tests

### Cache injection (mid-run fix)

The `/intent-layer` skill reverts generated AGENTS.md files at the end of its workflow (`git checkout HEAD -- .`). This caused intent_layer warmup to produce 0 files for graphiti and ansible.

Fix: manually created hierarchical AGENTS.md files mid-run and injected into cache-manifest.json:
- graphiti: CLAUDE.md + 5 child AGENTS.md (driver, search, llm_client, namespaces, server)
- ansible: CLAUDE.md + 6 child AGENTS.md (modules, plugins, executor, playbook, parsing, test)

This was validated by log output: "restored from cache 6 file(s) in 0.0s" for subsequent graphiti tasks.

---

## Cross-repo synthesis (all runs)

### The prompt_source hypothesis

Context helps most when the agent must navigate the codebase (commit_message), less when it follows a traceback (failing_test). But the effect size varies by repo complexity:

- Simple repos (pdm): context is distraction
- Medium repos (graphiti): flat context hurts, hierarchical helps
- Complex repos (ansible): hierarchical context is the difference between 0% and 100% on some tasks

### Flat vs hierarchical

| Finding | Evidence |
|---------|----------|
| Flat context can actively hurt | graphiti: flat 30% vs none 53% |
| Hierarchical context mitigates flat's harm | graphiti: intent 40% vs flat 30% |
| Hierarchical helps most on complex codebases | ansible human-to-bytes: 0% → 100% |
| Neither helps simple tasks | Many tasks at 100% ceiling across all conditions |
| Neither helps when traceback gives the answer | failing_test tasks show ~50% regardless |

### Key difference from the AGENTbench paper

The paper (arxiv 2602.11988v1) found that flat context files hurt performance. Our data agrees: **flat context can hurt** (graphiti -23pp). But hierarchical context (Intent Layer) is different — it provides focused, relevant information without the noise. On graphiti, intent_layer recovered 17pp of the damage flat context caused.

### Statistical power

With 73 infrastructure errors eating 30% of items and only 3 reps per condition, Wilson CIs are wide (~20pp). Only one individual task reached significance (`fix-ansiblemodule-human-to-bytes`, p < 0.10).

To reach significance at the aggregate level, we'd need:
- Fix data quality issues (recover ~70 items from infrastructure errors)
- Increase to 5+ reps per condition
- Add 2-3 more repos with 10+ tasks each
- Focus on medium-complexity repos where context has the most signal

### What we learned

1. Context files aren't categorically good or bad — it depends on the context's quality and relevance
2. Flat dumps of entire codebases can be worse than no context at all
3. Hierarchical, directory-scoped context helps when the agent needs to navigate
4. The module isolation boundary in ansible is the perfect example: a single AGENTS.md entry pointing the agent to `module_utils/` enabled 3/3 success on a task where none achieved 0/3

---

## Run 4 experiments (2026-02-18): Delivery mechanism deep-dive

**Goal**: Understand WHY intent_layer tokens ≈ none tokens, and fix the delivery mechanism.

### Key discoveries

#### 1. Claude Code auto-loads CLAUDE.md but NOT AGENTS.md

Confirmed via debug hook and token analysis. AGENTS.md files sit on disk passively.
Hooks inject ~500 tokens of Pitfalls — negligible at 193k total context.

#### 2. Inlining all AGENTS.md into CLAUDE.md hurts performance

Dumping 6 AGENTS.md files into CLAUDE.md (ansible) increased tokens to 247k but scored 0/5.
The irrelevant subsystem content (executor, playbook, parsing) drowns out the useful signal.
Reverted — inlining is worse than the pull model.

#### 3. The "pull" model is unreliable but works when it fires

| Run | Tokens | Result | Agent behavior |
|-----|--------|--------|----------------|
| 3-rep (113421) | 383k (+98%) | 2/3 (67%) | Claude read AGENTS.md files |
| 10-rep (114342) | 196k (+1%) | 0/10 (0%) | Claude skipped AGENTS.md |
| 5-rep w/ Downlinks preamble | 241k (+25%) | 0/5 (0%) | Claude read CLAUDE.md but not child nodes |

When Claude voluntarily reads AGENTS.md (383k), it passes. When it doesn't (196k), it fails.
The Downlinks preamble helped token consumption (+25% instead of +1%) but still not enough.

#### 4. For failing_test tasks, context is irrelevant

Log analysis of ansible human-to-bytes shows ALL conditions follow the same pattern:
Read test → Grep function → Read source → Edit. No condition reads AGENTS.md.
The traceback provides a direct path; the difference between pass/fail is reasoning quality.

#### 5. Near-ceiling tasks show context as noise

PDM commit_message tasks (Run 2 signal): none 100%, flat 89%, intent 78%.
These tasks improved since Run 2 — the model solves them without context.
CI widths: none 23%, flat 35%, intent 42% — **more context = more variance**.

#### 6. Token efficiency is mixed

| Scenario | Context effect on tokens | Pass rate |
|----------|------------------------|-----------|
| fastmcp (medium tasks) | -20% to -22% | 100% all conditions |
| pdm resolution-excludes | +208% to +274% | 67% (worse than none) |
| pdm pylock-toml | -69% to -82% | 67-100% |

Context sometimes helps navigate faster, sometimes causes over-exploration.

### Coverage gap: module_utils

The ansible Intent Layer has NO AGENTS.md for `lib/ansible/module_utils/` — the directory
containing the bug. The 6 child nodes cover modules, plugins, executor, playbook, parsing,
and tests. This is a generation quality issue, not a delivery mechanism issue.

### Updated synthesis

| Finding | Evidence |
|---------|----------|
| Inlining all AGENTS.md is worse than selective reading | 0/5 with inline vs 2/3 when agent selectively reads |
| Preamble can nudge but not force file reads | +25% tokens vs +1%, but still 0/5 pass rate |
| Context adds variance on near-ceiling tasks | CI widths: none 23%, flat 35%, intent 42% |
| The "Goldilocks zone" for context: hard enough to need navigation, not so hard it's pure reasoning | failing_test on simple bugs = no benefit; commit_message on hard navigation = benefit |
| Coverage gaps in generation are critical | Missing module_utils AGENTS.md eliminates the benefit |

### Next steps for meaningful evaluation

1. **Find harder tasks** — current model solves most tasks without context
2. **Test on medium-complexity repos** where navigation genuinely helps (graphiti showed strongest differential)
3. **Fix Intent Layer generation** — ensure coverage of high-impact directories like module_utils
4. **Consider commit_message tasks on complex repos** — this is the sweet spot for context
5. **Increase to 5+ reps** — 3 reps can't distinguish 67% from 100% with overlapping CIs

---

## Run 6 (2026-02-18): Push-on-read hook on graphiti

**Goal**: Test whether injecting AGENTS.md content during file reads (push-on-read) improves intent_layer over the pull model.

### Setup

- **Hook change**: PreToolUse fires on `Read|Grep|Edit|Write` (was Edit-only). Script `push-on-read-hook.sh` finds covering AGENTS.md, extracts Contracts/Pitfalls/Patterns, injects as `additionalContext`.
- **Task config**: `graphiti-signal.yaml` — 7 commit_message tasks (strongest signal from Run 3)
- **Design**: 7 tasks × 3 conditions × 1 rep = 21 items, --parallel 4, --timeout 450

### Results

| Task | none | flat_llm | intent_layer | none_t | flat_t | intent_t |
|------|------|----------|--------------|--------|--------|----------|
| fix-datetime-comparison | PASS | FAIL | FAIL | 127s | 450s | 450s |
| fix-limited-number-of-edges | FAIL | FAIL | FAIL | 450s | 450s | 450s |
| sanitize-pipe-slash | PASS | FAIL | FAIL | 118s | 450s | 450s |
| escape-group-ids | PASS | PASS | PASS | 162s | — | — |
| filter-falsey-values | FAIL | FAIL | **PASS** | 450s | 450s | — |
| validate-nodes-edges | PASS | FAIL | FAIL | 258s | 450s | 450s |
| fix-entity-extraction | PASS | PASS | PASS | 134s | — | — |

| Condition | Pass rate |
|-----------|-----------|
| none | 5/7 (71%) |
| flat_llm | 2/7 (28%) |
| intent_layer | 3/7 (42%) |

Timeouts: 11/21 (52%). All failures are timeouts.

### Key findings

#### 1. Context still hurts on graphiti (consistent with Run 3)

Run 3 (Edit-only): none 89%, flat 50%, intent 67%.
Run 6 (push-on-read): none 71%, flat 28%, intent 42%.
Relative ordering preserved: none > intent > flat. Push-on-read didn't fix it.

#### 2. CLAUDE.md's `make test` instruction is a confounding factor

Log analysis revealed the mechanism: CLAUDE.md says `make test` for running tests. In the eval
Docker environment, `make test` runs the full suite (slow, ~60s+ setup). The `none` condition,
without this guidance, discovers specific test files and runs targeted tests (fast, ~15s).

- sanitize-pipe-slash (none, 118s): ran `pytest tests/driver/test_falkordb_driver.py` → targeted
- sanitize-pipe-slash (intent_layer, 450s): ran `make test` → broad, timed out

The context gives Claude a correct-but-slow test strategy. Without context, Claude finds the
fast path by exploring the test directory structure.

#### 3. One unique intent_layer win: filter-falsey-values

Only intent_layer passed (none and flat_llm both timed out). The intent_layer Claude explored
more thoroughly (23 turns, $0.81) and eventually found the right multi-file fix. The none
condition made edits but couldn't get tests to pass within the timeout. This is the kind of
complex multi-file task where context should help navigation.

#### 4. Push-on-read fires too broadly

The hook fires on every Read/Grep, including reads of CLAUDE.md itself (redundant — already
auto-loaded). For files in `graphiti_core/utils/maintenance/` (4 of 7 tasks), the hook walks up
to root CLAUDE.md (no child AGENTS.md covers that path), injecting the same root context
that's already in Claude's window. Only FalkorDB driver tasks (sanitize-pipe-slash, escape-group-ids)
have a child AGENTS.md (`driver/AGENTS.md`).

### Confounding factors

1. **`make test` in CLAUDE.md** — both flat_llm and intent_layer see this and use it, burning
   time on broad test execution. This affects all context conditions equally.
2. **450s timeout** — many tasks need >450s with context (test setup alone is ~60s in Docker).
   Increasing to 600s might flip some FAIL→PASS.
3. **1 rep only** — filter-falsey unique win could be variance. The killed Run 6 attempt
   (different seed) showed datetime passing for intent_layer.
4. **AGENTS.md coverage gap** — `graphiti_core/utils/` and `graphiti_core/utils/maintenance/`
   have no AGENTS.md, so 4/7 tasks only get root context from push-on-read.

### Comparison: Pull (Run 3) vs Push-on-read (Run 6)

| Metric | Run 3 (Edit-only) | Run 6 (push-on-read) |
|--------|-------------------|---------------------|
| intent_layer pass rate | 67% (12/18) | 42% (3/7) |
| none pass rate | 89% (16/18) | 71% (5/7) |
| intent−none gap | −22pp | −29pp |
| Timeout rate | ~30% | 52% |

Push-on-read made things slightly worse, though task sets differ (Run 3 had 6 valid tasks,
Run 6 has 7 including fix-limited-number-of-edges which is very hard).

### Implications for Intent Layer delivery

The push-on-read mechanism is technically sound but exposed a deeper problem: the content
being pushed isn't matched to the eval environment. Development instructions in CLAUDE.md
(`make test`, `uv sync`) are optimized for interactive local development, not for the eval's
Docker environment with 450s timeouts. The context helps when it provides navigation cues
(filter-falsey-values) but hurts when it provides slow-path instructions.

### Next experiments

1. **Strip development commands**: Create eval-specific CLAUDE.md that removes `make test`
   and similar instructions, keeping only architecture and navigation info.
2. **Only push child AGENTS.md**: Skip injection when covering node is root CLAUDE.md
   (already auto-loaded), only inject when a child AGENTS.md exists.
3. **Add missing coverage**: Create `graphiti_core/AGENTS.md` and `graphiti_core/utils/AGENTS.md`
   to cover the 4 tasks currently getting only root context.
4. **Increase timeout**: 600s to account for Docker test setup overhead.
5. **3+ reps**: Need multiple reps to separate signal from noise.
