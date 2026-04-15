# AGENTbench Native Adapter

**Date**: 2026-02-24
**Status**: Brainstorm complete, ready for planning

## What we're building

A native adapter in our eval harness that loads the AGENTbench paper's 138
instances directly from HuggingFace and runs them with four conditions
(none, flat_llm, human, intent_layer) using their test infrastructure but our
resilience and statistics pipeline.

## Why this approach

The paper (arxiv 2602.11988v1) claims context files hurt agent performance.
Our prior runs suggest flat context hurts but hierarchical context is neutral
to helpful. To make that case credibly:

- We need to run the **same tasks** they did, not cherry-picked ones
- We need to use their **test evaluation** (both instance tests AND repo
  regression checks), not just exit-code pass/fail
- We need the **statistical rigor** they lack: multiple reps, paired tests,
  per-task significance testing

Running 138 instances x 4 conditions at their fidelity, with our stats, is
the strongest possible response to the paper.

## Key decisions

### 1. Use their test infrastructure verbatim

Their instances include pre-built Python test runner scripts
(`repo_test_runner`, `test_file_runner`) that emit structured JSON results.
We'll execute these inside Docker exactly as they do, rather than converting
to our shell-command-and-exit-code approach. This eliminates the "different
test criteria" objection entirely.

### 2. Use their problem descriptions

Their task text is curated markdown extracted from PRs. We'll pass it to
Claude verbatim rather than regenerating from commit messages or issues.
Same task statement = same experiment, just with an added condition.

### 3. Use their Docker images on x86 cloud

Their pre-built images (`tgloaguen/planbenchx86_*`) are x86-only. We'll run
on EC2 (or similar x86 cloud) rather than fighting Rosetta/QEMU emulation
on ARM Macs. This eliminates timing artifacts and architecture mismatches.

Fallback: replicate their setup_commands on base images if their images go
stale.

### 4. Four conditions

| Condition | Context source | Notes |
|-----------|---------------|-------|
| `none` | All .md + .github + docs stripped | Matches their baseline exactly |
| `flat_llm` | Their cached generated files from `agentbench_traces.tar.zst` | Exact same files they tested — no regeneration variance |
| `human` | Developer-written files from git history | Their `human_planner.py` approach: fetch from future commits after base_sha |
| `intent_layer` | Hierarchical AGENTS.md generated at HEAD | See "Data leakage" section below |

Adding `human` as a 4th condition is low effort (the instances include the
developer's original files) and gives us a direct calibration point against
their published numbers.

### 5. Flat LLM uses their cached files

Rather than regenerating with our prompt (which introduces variance), we use
their pre-generated files from `agentbench_traces.tar.zst` → `extracted_plans.json`.
This is the exact content they tested. Zero regeneration variance.

### 6. Phased execution

**Phase 1**: All 138 instances x 1 rep x 4 conditions = 552 runs.
Replicates their experiment design plus our new conditions.
Validates our infrastructure against their published numbers.

**Phase 2**: Deep-dive on instances where intent_layer shows signal.
3-5 reps on interesting tasks for Fisher per-task analysis.

### 7. Doc stripping matches theirs

They strip ALL markdown (`find . -name "*.md" -delete`) plus .github/ and
docs/. We currently only strip context files. For this experiment, we match
their stripping exactly — our `none` baseline must equal their `none`.

### 8. Temperature and repetitions

Phase 1 runs at temperature=0 for direct comparison to their n=1 numbers.
Phase 2 runs at default temperature with 3-5 reps for variance estimation.
Both are reported.

### 9. Data leakage strategy for Intent Layer

**Problem**: Intent Layer generated at HEAD contains knowledge derived from
the entire git history, including the very fixes being tested. AGENTS.md
might effectively teach Claude the answer.

**The paper has the same issue**: Their `human_planner.py` fetches
developer-written AGENTS.md/CLAUDE.md from future commits after `base_sha`.
The developer who wrote those files had full knowledge of the codebase
including the fixes. The paper doesn't acknowledge or control for this.

**Our approach**:
- **Phase 1**: Generate Intent Layer at HEAD (same temporal stance as their
  human condition). Accept the leakage — if we beat their human condition
  with the same leakage profile, the comparison is valid.
- **Phase 2 robustness check**: Generate once per repo at a pre-dataset
  cutoff commit (before any instance's base_sha). 12 generations instead
  of 138. Tests whether results hold without fix-specific knowledge.

This is defensible: we're comparing our approach to theirs under identical
temporal conditions. If someone objects to leakage, the objection applies
equally to their human condition.

## What changes in our harness

The adapter sits alongside the existing YAML-based task runner, not replacing
it. Key new components:

- **AgentbenchLoader**: Loads instances from HuggingFace dataset, converts to
  internal representation
- **AgentbenchEvaluator**: Runs their test scripts inside Docker, parses JSON
  results, maps to our pass/fail + regression-check format
- **Doc-strip mode**: Match their aggressive stripping (all .md, .github, docs/)
- **Condition injector**: Four conditions — none strips everything, flat_llm
  uses their cached files, human uses developer files from git, intent_layer
  adds hierarchy

Our existing infrastructure stays: circuit breaker, supervisor loop, monitor,
checkpoint/resume, Fisher/McNemar stats pipeline.

## Methodological alignment summary

| Dimension | Theirs | Ours (with adapter) | Gap |
|-----------|--------|---------------------|-----|
| Tasks | 138 from 12 repos | Same 138 | None |
| Docker env | Pre-built x86 images | Same images on x86 cloud | None |
| Test eval | Instance + repo regression | Same scripts | None |
| Problem text | Curated markdown | Same text | None |
| Doc stripping | All .md + .github + docs | Same | None |
| Flat LLM files | Generated + cached | Their cached files | None |
| Human files | Developer files from git | Same approach | None |
| Conditions | none, LLM, human | none, flat_llm, human, intent_layer | Superset |
| Agent | Claude, Codex, Qwen, Gemini | Claude only | Narrower |
| Temp/reps | temp=0, n=1 | Phase 1: temp=0 n=1; Phase 2: default, n=3-5 | Ours is superset |
| Stats | Aggregate % only | Aggregate + Wilson CI + McNemar + Fisher per-task | Ours is superset |
| Resilience | None (move on if it fails) | Circuit breaker + supervisor + monitor | Ours is superset |
| IL temporal | N/A | Phase 1: HEAD; Phase 2: pre-cutoff robustness | Novel |

## Resolved questions

1. **x86 Docker images** → Run on EC2 or similar x86 cloud.
2. **Flat LLM generation** → Use their cached files from traces archive.
3. **Human condition** → Yes, include as 4th condition for calibration.
4. **Data leakage** → Phase 1 at HEAD (matches their temporal stance for
   human); Phase 2 robustness check at pre-dataset cutoff.

## Open questions

1. **Budget.** Phase 1: ~552 calls x ~$1.50 = ~$830. Phase 2: depends on
   how many tasks show signal. Total likely $1000-1800.

2. **Wall clock time.** At 1800s timeout, 4 workers, 552 runs: worst case
   ~38 hours for phase 1. Realistic (not all timeout): ~16-24 hours.

3. **EC2 instance type.** Need Docker + Claude API access. Probably
   c5.xlarge or similar. Cost ~$0.17/hr x 24hr = ~$4.

4. **Intent Layer quality per repo.** Some of the 12 repos may not benefit
   from hierarchical context (small repos, flat structure). Worth checking
   which repos are good IL candidates before running.
