# AGENTbench Replication: Disputing "Context Files Hurt Agent Performance"

**Date**: 2026-02-16
**Status**: Brainstorm complete, ready for planning

## What We're Building

A rigorous replication study using the eval-harness to dispute the findings of "Evaluating AGENTS.md" (arxiv 2602.11988v1). The paper claims LLM-generated context files reduce task success rates and increase inference cost by 20%+. We believe the paper tested the wrong kind of context files — flat, generic overviews from `/init` — and that Intent Layer's hierarchical, pitfall-focused approach produces different results.

**Approach**: Minimal-diff replication (same repos, same task types, same metrics) with enhanced analysis layered on top (discovery speed, complexity breakdown, AGENTS.md read tracking).

## Why This Approach

The paper's methodology has a specific blind spot: it treats all LLM-generated context files as equivalent. Their "LLM-generated" condition uses each agent's default initialization (`/init`, `codex --init`), which produces a single flat file with a generic overview. Intent Layer produces a hierarchy of focused nodes with contracts, pitfalls mined from git history, and entry points.

The paper's own data supports our thesis — human-written files outperformed LLM-generated files for all four agents (+4% vs -2%). Intent Layer's approach is closer to human-written quality because it:
- Mines git history for real pitfalls (not generic advice)
- Creates multiple focused nodes (not one dump of everything)
- Loads only relevant ancestors per task (T-shaped context, not full project dump)

By using their exact repos and task methodology, we produce the most credible counter: "same benchmark, better context files, different results."

## Key Decisions

### 1. Three conditions: None / Flat LLM / Intent Layer
- **None**: Strip all context files from repo (matches paper's "None" condition)
- **Flat LLM**: Generate a single CLAUDE.md using a generic prompt that mimics `/init` output (matches paper's "LLM" condition)
- **Intent Layer**: Full hierarchical generation using Intent Layer skill (our differentiator)
- Decided against adding "Human-written" as a 4th condition — adds complexity and the paper already shows those help. Our argument is that Intent Layer can match or beat human-written quality.

### 2. Use the paper's 12 AGENTbench Python repos
- Direct comparability is the priority
- Need to extract repo names from the paper (tables, appendix, supplementary materials)
- All must be public, have test suites, have enough PRs to mine

### 3. Start small, iterate
- Pilot: 15-20 tasks from 2-3 repos
- Validate pipeline works end-to-end
- Check early signal before scaling to 50-100+ tasks
- Keeps initial cost under $100

### 4. Enhanced metrics (layered on after base replication works)
- **Discovery speed**: Steps before Claude first touches a file in the fix commit's patch
- **Complexity breakdown**: Report results per category (simple_fix / targeted_refactor / complex_fix)
- **AGENTS.md read tracking**: Which nodes Claude actually reads (already partially implemented)
- These add depth to the blog post without changing the core comparison

### 5. Output: public blog post
- Data-driven rebuttal with charts
- Show methodology transparently
- Include raw results for reproducibility
- Aimed at AI engineering community

## Open Questions

1. **Which specific repos did the paper use?** Need to extract from paper. They mention 12 Python repos with 400+ PRs, developer-written context files, post-August 2025. May need to check the paper's appendix, GitHub, or contact authors.

2. **How to generate the "Flat LLM" condition?** Options:
   - Run Claude's actual `/init` command (most faithful to paper)
   - Use a generic prompt that produces similar output (more controlled)
   - We should check what `/init` actually generates and match it

3. **Task mining approach**: Use `eval-harness scan` or replicate the paper's more complex PR filtering pipeline? The paper uses an LLM to select "deterministic, testable" PRs and generates custom tests. Our scanner mines existing test-backed bug fixes. Different but arguably more realistic.

4. **Statistical significance**: With 15-20 tasks in the pilot, can we make meaningful claims? May need bootstrapping or effect-size analysis rather than simple averages.

5. **Model version**: Paper uses Sonnet-4.5 (temperature=0). We should match this or document any difference.

## Eval Harness Changes Needed

### Must-have for pilot
- [ ] Add `FLAT_LLM` condition to `Condition` enum and `task_runner.py`
- [ ] Add flat CLAUDE.md generation prompt to `prompt_builder.py`
- [ ] Create task YAML files for 2-3 of the paper's repos
- [ ] Ensure `WITHOUT_SKILL` condition strips any existing context files

### Nice-to-have (enhanced analysis)
- [ ] Discovery speed metric (needs fix_commit patch file list)
- [ ] Per-category result breakdown in reporter
- [ ] Better AGENTS.md read tracking
- [ ] Cost calculation (tokens to USD based on model pricing)

### Infrastructure
- [ ] Verify Docker setup works for Python repos (current example is Express.js/Node)
- [ ] Ensure `eval-harness scan` works well for Python repos with pytest

## What We're NOT Building

- Not testing multiple agents (Claude only — paper's multi-agent comparison is interesting but orthogonal to our claim)
- Not reproducing the paper's custom test generation pipeline (we use existing tests)
- Not building a formal academic paper (blog post is the target)
- Not testing non-Python repos in this round (would weaken direct comparison)
- Not doing ablation studies on Intent Layer components (save for follow-up)
