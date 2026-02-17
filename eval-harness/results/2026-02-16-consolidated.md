# AGENTbench Replication: fastmcp (8 tasks, 3 conditions)

**Date**: 2026-02-16
**Repo**: https://github.com/jlowin/fastmcp
**Model**: Claude Sonnet 4.5 (default)
**Timeout**: 300s per task
**Docker**: python:3.11-slim

## Results

| # | Task ID | Category | Lines | none | flat_llm | intent_layer |
|---|---------|----------|-------|------|----------|--------------|
| 1 | merge-pull-request-3198 | complex_fix | 852 | PASS (219s/54tc) | PASS (207s/50tc) | PASS (199s/51tc) |
| 2 | fix-ty-0017-diagnostics | complex_fix | 852 | TIMEOUT (300s/64tc) | TIMEOUT (300s/54tc) | TIMEOUT (300s/44tc) |
| 3 | merge-pull-request-3195 | simple_fix | 29 | PASS (126s/19tc) | PASS (132s/19tc) | PASS (131s/19tc) |
| 4 | fix-include_tags/exclude_tags | targeted_refactor | 109 | TIMEOUT (300s/37tc) | FAIL (152s/17tc) | **PASS (173s/16tc)** |
| 5 | fix-stale-request-context | complex_fix | 206 | TIMEOUT (300s/42tc) | TIMEOUT (300s/35tc) | TIMEOUT (300s/39tc) |
| 6 | docs-fix-stale-get_-references | targeted_refactor | 101 | TIMEOUT (300s/45tc) | TIMEOUT (300s/20tc) | TIMEOUT (300s/35tc) |
| 7 | fix-guard-client-pagination | complex_fix | 338 | INFRA* | TIMEOUT (300s/19tc) | INFRA* |
| 8 | fix-snapshot-access-token | complex_fix | 235 | PASS (117s/15tc) | PASS (105s/12tc) | PASS (113s/13tc) |

*Task 7 infrastructure error: pre-validation timeout (Docker setup + pytest > 120s for test_pagination.py)

## Success Rates

### Excluding task 7 (infrastructure error)

| Condition | Pass | Total | Rate |
|-----------|------|-------|------|
| none | 3 | 7 | 42.9% |
| flat_llm | 3 | 7 | 42.9% |
| **intent_layer** | **4** | **7** | **57.1%** |

### Including task 7 (infra = failure)

| Condition | Pass | Total | Rate |
|-----------|------|-------|------|
| none | 3 | 8 | 37.5% |
| flat_llm | 3 | 8 | 37.5% |
| **intent_layer** | **4** | **8** | **50.0%** |

## Key Finding: Task 4 Differentiates

Task 4 (`fix-include_tags/exclude_tags`) is where intent_layer uniquely succeeds:

- **none** timed out: couldn't find the right code in 300s (37 tool calls exploring)
- **flat_llm** found code but wrong fix: tests failed after 152s (17 tool calls)
- **intent_layer** fixed it correctly: 173s with 16 tool calls

This is a targeted_refactor (109 lines across 3 files) in the MCPConfig system.
The AGENTS.md files gave Claude the component map it needed to navigate the
multi-file fix correctly.

## Comparison with Paper

The AGENTbench paper (arxiv 2602.11988v1) claims context files hurt agent performance.

Our results suggest a more nuanced picture:
- **Flat context = no help**: flat_llm matches none exactly (42.9% vs 42.9%)
- **Hierarchical context = helps**: intent_layer outperforms both (57.1%)

The paper tested flat, single-file context. Our hierarchical approach with
directory-specific AGENTS.md files provides targeted guidance that a single
CLAUDE.md can't match.

## Task Categorization

| Difficulty | Tasks | none | flat_llm | intent_layer |
|-----------|-------|------|----------|--------------|
| Easy (all pass) | 1, 3, 8 | 3/3 | 3/3 | 3/3 |
| Medium (partial) | 4 | 0/1 | 0/1 | **1/1** |
| Hard (all timeout) | 2, 5, 6 | 0/3 | 0/3 | 0/3 |
| Infra error | 7 | - | 0/1 | - |

The differentiation happens on medium-difficulty tasks where navigating the
codebase matters — exactly where hierarchical context files add value.

## Notes

- Task 1 none from separate run (cache concurrency bug fixed between runs)
- Tasks 1-2 use commit_message prompt (no behavioral test); tasks 3-8 use failing_test
- Test injection: fix_commit test files injected into pre_fix workspaces for tasks 3-8
- Context files cached at repo level (generated once, reused across tasks)
- Sample size is small (7-8 tasks); results are directional, not conclusive
