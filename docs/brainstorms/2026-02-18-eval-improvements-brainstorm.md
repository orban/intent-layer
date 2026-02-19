---
date: 2026-02-18
topic: eval-improvements
deepened: 2026-02-19
---

# Eval harness and Intent Layer improvements

## Enhancement summary

**Deepened on:** 2026-02-19
**Sections enhanced:** 6
**Research agents used:** architecture-strategist, eval-harness-explorer, best-practices-researcher, spec-flow-analyzer, context-injection-researcher

### Key improvements from research
1. Resolved all 4 open questions (preamble position, cache strategy, repo scope, rep count)
2. Identified 5 specific risks of preamble injection with concrete mitigations
3. Found relevant statistics paper proving current CI method is wrong for small N
4. Mapped exact code change points (line numbers) for Phase 2 implementation
5. Discovered prompt ordering matters: task description FIRST, context AFTER

### New considerations discovered
- Current CLT-based CIs systematically underestimate uncertainty at N<100 — switch to Wilson CIs + Fisher's exact test
- Preamble position should be reversed: put bug description first, context second (attention dilution risk)
- Need a 4th condition (`intent_layer_preamble_only`) to isolate preamble effect from files-on-disk effect
- Push-on-read hook should remain as secondary delivery even with preamble injection

---

## What we're building

Two-phase improvement to the eval harness and Intent Layer content, based on findings from Runs 1-7 of the AGENTbench replication.

**Phase 1 — Fix the plumbing**: Eliminate known data quality issues and content confounds so we get clean signal from experiments. This is YAML fixes, coverage gap fills, and stripping dev-specific commands.

**Phase 2 — Solve delivery**: Build a preamble injection mechanism that delivers child AGENTS.md content directly into Claude's context, bypassing the unreliable pull model where Claude must voluntarily read files.

## Why this approach

The data so far shows three things clearly:

1. **Flat context hurts** (graphiti: -23pp vs none). Hierarchical mitigates (+10pp recovery) but doesn't fully overcome.
2. **Delivery is unreliable**. Run 4 proved that when Claude reads AGENTS.md (383k tokens), it passes. When it doesn't (196k tokens), it fails. The content works — it just doesn't get read.
3. **Confounds are polluting signal**. 30% infra errors, dev commands causing slow test strategies, coverage gaps meaning Intent Layer has nothing to offer for the actual bug directories.

We can't evaluate delivery fixes (Phase 2) until the data is clean (Phase 1). And we can't evaluate content changes until delivery is reliable. So: plumbing first, delivery second.

## Key decisions

- **Fix task configs before adding reps**: Invalid tasks and wrong paths waste every rep. Fix the YAML first.
- **Focus on graphiti for differential signal**: It's the repo where flat hurts and intent recovers — the strongest A/B signal we have.
- **Fill coverage gaps in AGENTS.md**: ansible missing `module_utils/`, graphiti missing `utils/` and `utils/maintenance/`. These are exactly where bugs live.
- **Strip dev commands from eval CLAUDE.md**: `make test` is correct for local dev but harmful in Docker eval (triggers 60s full suite instead of targeted tests). Either remove or replace with Docker-appropriate guidance.
- **Keep both task types (commit_message and failing_test) for now**: The signal that context only helps navigation tasks is interesting but not yet strong enough to split the evaluation.
- **Phase 2: child-only preamble injection**: Root CLAUDE.md is auto-loaded. Only inject child AGENTS.md content. This avoids the "inlining everything" failure from Run 4 (0/5).

## Phase 1 specifics

### Task config fixes

| Repo | Fix | Why |
|------|-----|-----|
| graphiti.yaml | Add `--ignore=mcp_server/tests` | Collection errors from mcp_server test dir |
| graphiti.yaml | Drop `preserve-all-signatures` | Overly strict, causes false negatives |
| ansible.yaml | Drop `fix-local-connection` | Task is invalid (test passes at pre-fix commit) |
| ansible.yaml | Fix `fix-clearlinux` test_file path | IsADirectoryError from wrong path |
| ansible.yaml | Scope test_command | Broad pytest catches unrelated failures |

### Coverage gaps to fill

| Repo | Missing node | Why it matters |
|------|-------------|----------------|
| graphiti | `graphiti_core/AGENTS.md` | 4/7 eval tasks live here |
| graphiti | `graphiti_core/utils/AGENTS.md` | utils/maintenance is a common bug location |
| ansible | `lib/ansible/module_utils/AGENTS.md` | Star result task lives here; 0/3 → 3/3 with context |

#### Research insight: coverage gap strategy

The coverage gaps aren't just missing files — they're the reason the push-on-read hook fires but only returns root-level context. For files in `graphiti_core/utils/maintenance/`, the hook walks up to the root CLAUDE.md (no child AGENTS.md covers that path), so it injects content Claude already has. Adding `graphiti_core/AGENTS.md` and `graphiti_core/utils/AGENTS.md` changes this: the hook would inject subsystem-specific Pitfalls and Contracts.

When creating these AGENTS.md files, focus on:
- **Module boundaries** (what imports from where, module responsibilities)
- **Pitfalls** specific to that subsystem (the content type that proved most useful in Run 4)
- **Contracts** (what functions accept/return, invariants)
- Skip workflow/setup content — it's the biggest confound

Cache injection note: after creating these files, they must be injected into `cache-manifest.json` (the `/intent-layer` skill reverts generated files; manual creation + cache injection is required).

### Dev command cleanup

Strip or adapt these from eval CLAUDE.md files:
- `make test` → remove (let Claude discover test commands or use targeted pytest)
- `uv sync` → remove (Docker handles dependency setup)
- Any `pip install -e .` instructions → remove (pre-installed in Docker)

#### Research insight: the `make test` confound is bigger than it looks

In graphiti, `make test` runs the full test suite (~60s setup). The `none` condition, without this instruction, discovers specific test files and runs targeted tests (~15s). This means `none` has a *structural advantage* over both context conditions — it's faster because it doesn't know about `make test`. Removing `make test` from CLAUDE.md doesn't just fix a confound; it levels the playing field for the first time.

Consider also: replace with a hint like "Run only the specific test file mentioned in the problem" rather than removing all test guidance. This gives context conditions the same targeted-test advantage that `none` gets by default.

### Statistical methodology upgrade

**Problem**: Current CIs use CLT-based normal approximation. The paper "Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints" (Bowyer et al., 2025) shows these systematically underestimate uncertainty at small N, producing error bars that are too tight.

**Fix for Phase 1 reporting:**
- Switch to **Wilson score confidence intervals** for per-condition pass rates (valid at any N, unlike Wald/CLT)
- Use **Fisher's exact test** for pairwise condition comparisons (none vs intent_layer) — exact p-values, no approximation needed
- Report **exact binomial CIs** alongside Wilson CIs for transparency
- At N=5 reps: Wilson CI for 3/5 (60%) is [23%, 88%] — much wider than CLT would suggest
- At N=10 reps: Wilson CI for 6/10 (60%) is [31%, 83%] — still wide but starting to be useful
- Minimum for detecting a 20pp effect (40% vs 60%): N≈25 per cell at 80% power (Fisher's exact)

**Practical implication**: With 5 reps, we can only detect very large effects (>40pp difference). Don't over-interpret small differences between conditions. The current results claiming ~20pp differences (e.g., none 63% vs intent 66%) are well within noise — the CIs overlap massively.

**Implementation**: `scipy.stats.fisher_exact()` for 2x2 tables, `statsmodels.stats.proportion.proportion_confint(method='wilson')` for CIs. Both are one-line additions to the reporter.

**References:**
- [Don't Use the CLT in LLM Evals (arxiv 2503.01747)](https://arxiv.org/abs/2503.01747)
- [Fisher's Exact Test for Small Samples (DataCamp)](https://www.datacamp.com/tutorial/fishers-exact-test)

## Phase 2 specifics (after Phase 1 data is clean)

### Preamble injection mechanism

Build a script that:
1. Takes a target file path
2. Walks ancestors using existing `walk_ancestors.sh`
3. Collects child AGENTS.md content (NOT root CLAUDE.md — already auto-loaded)
4. Concatenates into a preamble block
5. Injects into Claude's initial prompt or system context

#### Research insight: architecture review resolved the open questions

**Q: System prompt addition or user prompt prepend?**
A: **User prompt prepend** (Alternative B). Matches the existing preamble pattern — `FLAT_PREAMBLE` and `INTENT_LAYER_PREAMBLE` are already prepended strings. Simpler than `--append-system-prompt`, visible in logs, and cacheable by the prompt builder. If prompt position experiments later show system prompt helps, it's a one-line change to switch.

**Q: Where in the pipeline?**
A: **In `task_runner._build_prompt()`** (lines 963-1007). Add a `_collect_preamble_content(workspace, task)` method that:
1. Walks ancestors from `task.test_file`
2. For each AGENTS.md in the ancestor chain (excluding root), extracts Pitfalls + Contracts sections
3. Truncates to 1.5k tokens, prioritizing nearest ancestor
4. Returns the content string

Pass this string to `prompt_builder.build_prompt_from_*()` as the `preamble` parameter. The prompt builder stays a pure string-assembly module — no filesystem I/O.

**Q: Cache strategy?**
A: **No separate cache.** The raw AGENTS.md files are already cached by `IndexCache`. Preamble assembly is cheap (<100ms: read a few files, extract sections, concatenate, truncate). The cache key would need the target path, giving low hit rates. Not worth the complexity.

**Key implementation detail — prompt ordering:**
Put the task description FIRST, context SECOND. Reverse the current pattern where preamble comes before the problem statement.

```
"Here is a bug to fix: [failing test / commit message]

Before fixing, review these known pitfalls for this subsystem:
[AGENTS.md Pitfalls + Contracts content]
```

Rationale: Claude's attention to the task description decreases as preamble length grows. The failing test output or commit message is the most important part. Context after the problem acts as "here's what you should know" rather than "here's what to think about before you see the problem."

### Eval harness changes for preamble testing

- Add a new delivery mode to task_runner: `preamble` (vs current `pull`)
- The preamble gets prepended to Claude's prompt
- Compare: `intent_layer_pull` (current) vs `intent_layer_preamble` (new)
- Keep `none` and `flat_llm` as baselines

#### Research insight: add a 4th condition to isolate the preamble effect

The architecture review identified an experimental confound: if `intent_layer_preamble` includes both files on disk AND preamble content, we can't attribute gains to either one alone. Add:

| Condition | Files on disk | Preamble in prompt | Push-on-read hook |
|-----------|--------------|-------------------|-------------------|
| `none` | No | No | No |
| `flat_llm` | Single CLAUDE.md | Pull instruction | No |
| `intent_layer` | Hierarchical AGENTS.md | Pull instruction | Yes |
| `intent_layer_preamble` | Hierarchical AGENTS.md | Inline content | Yes |

If `intent_layer_preamble` outperforms `intent_layer`, the gain is from delivery mechanism. If both are similar, the bottleneck was elsewhere.

Optional 5th condition for maximum isolation: `preamble_only` (inline content, NO files on disk, no hook). This tests whether the content alone — without any file-reading opportunity — is sufficient.

### Token budget for preamble

Run 4 showed inlining everything (all ancestors + siblings) hurt (0/5). The preamble must be selective:
- Only ancestors from root to target (T-shaped, no siblings)
- Skip root (already loaded)
- Target: <2k tokens of injected content per task

#### Research insight: 1.5k cap, nearest-ancestor-only, Pitfalls + Contracts

The architecture review recommends tightening the budget:

- **1.5k tokens, not 2k.** Current preambles are ~30-50 tokens. 1.5k is already a 30x increase. Start conservative, increase later if results warrant.
- **Fixed cap, not proportional.** Task complexity doesn't predict which AGENTS.md is useful. A 5-line Pitfall about `isinstance` checking is worth more than 2k tokens of architecture description.
- **Nearest ancestor only.** Including the full ancestor chain risks attention dilution. The most specific ancestor has the most relevant Pitfalls.
- **Sections: Pitfalls + Contracts only.** Skip Overview, Downlinks, and other sections — they're navigational, not operational. The push-on-read hook already proved that Pitfalls/Contracts/Patterns are the useful sections.

Concrete: `resolve_context.sh --sections "Contracts,Pitfalls" --compact` already does most of this. Shell out to it or reimplement the section extraction in Python.

### Risks of preamble injection

Five specific risks identified by the architecture review:

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Attention dilution** | Preamble pushes task description further from prompt start | Put task description FIRST, context AFTER |
| **Misleading context** | Wrong AGENTS.md selected (parent too general) | Only include nearest ancestor's Pitfalls |
| **Hook duplication** | Push-on-read injects same content preamble already contains | Accept small duplication (both extract same sections, content is short) |
| **Passive vs active reading** | Injected content may not integrate as deeply as actively-read content | Frame as directive: "Review these known pitfalls" not raw markdown dump |
| **Experimental confound** | Can't attribute gains to preamble vs files-on-disk | Add `intent_layer_preamble` as 4th condition to isolate effect |

### How other coding agents handle context injection

Research into SWE-agent, OpenHands, and Cursor reveals three delivery models:

| Tool | Model | Mechanism |
|------|-------|-----------|
| **SWE-agent** | Push (system prompt) | Custom agent-computer interface injects repo map and file contents into system prompt. Agent sees context before any action. |
| **OpenHands** | Push (event log) | Event-sourced state model with deterministic replay. Context persists across actions via immutable event stream. |
| **Cursor rules (.mdc)** | Push (auto-inject) | Rules files with glob patterns auto-inject matching content when files are opened. Closest to push-on-read hook model. |
| **Claude Code (CLAUDE.md)** | Auto-load root only | Root CLAUDE.md auto-loaded. Children (AGENTS.md) are passive — must be explicitly read. |

The industry trend is clearly toward **push models**. SWE-agent and OpenHands both inject context before the agent starts. Cursor's .mdc rules are a push-on-access model similar to the push-on-read hook, but with tighter file-pattern matching.

This validates the preamble injection direction: move from Claude Code's passive pull model toward the push model that other frameworks use successfully.

**References:**
- [OpenHands Software Agent SDK (arxiv 2511.03690)](https://arxiv.org/abs/2511.03690)
- [OpenHands Docs](https://docs.openhands.dev/sdk)

## Open questions (resolved)

~~Should preamble be injected as system prompt addition or as a "context file" passed via `--context` flag to Claude CLI?~~
**Resolved:** User prompt prepend. Matches existing pattern, simpler, visible in logs.

~~How do we handle the cache for preamble content? Same index_cache, or separate?~~
**Resolved:** No separate cache. Reuse IndexCache for raw files. Assembly is cheap and task-specific.

~~Should we run Phase 1 on graphiti only (strongest signal) or all three repos?~~
**Resolved:** Start with graphiti (strongest differential signal). Add ansible if graphiti results are clean and we want broader validation. Skip pdm (near-ceiling, context adds noise there).

~~What rep count for Phase 1 clean run? 5 reps gives ~15pp CI width, 10 reps gives ~10pp.~~
**Resolved:** 5 reps minimum. With Wilson CIs, 5 reps on 7 tasks gives 35 items per condition — enough to detect 30pp+ effects. 10 reps if time/budget allows.

## Remaining open questions

- Should the preamble include a `Patterns` section (in addition to Pitfalls + Contracts)? Patterns might help with navigation but increase token count.
- For `failing_test` tasks where traceback gives a direct path to the bug, should we still inject preamble? It might be pure noise for these tasks.
- How to handle tasks where `test_file` is empty or points to a directory? Ancestor walking needs a file path.

## Next steps

→ `/workflows:plan` for Phase 1 implementation details
