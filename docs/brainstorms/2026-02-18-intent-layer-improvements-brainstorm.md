---
date: 2026-02-18
topic: intent-layer-improvements
refined: 2026-02-18
---

# Intent Layer improvements based on eval results

## The hypothesis

The AGENTbench paper (arxiv 2602.11988v1, repo: [eth-sri/agentbench](https://github.com/eth-sri/agentbench)) tested whether **onboarding context** (commands, architecture, style guides) helps agents fix bugs. It found it doesn't — and sometimes hurts.

We propose testing whether **operational context** (module boundaries, invariants, known failure modes) helps agents fix bugs. This is a fundamentally different kind of information that the paper never tested.

| | Paper's "LLM" condition | Our proposal |
|---|---|---|
| **Content type** | Onboarding (commands, architecture, style) | Operational (rules, boundaries, contracts) |
| **Sourced from** | Top-down codebase analysis | Bottom-up failure modes (git history, bug patterns) |
| **Structure** | Single flat file (duplicated to both AGENTS.md and CLAUDE.md) | Hierarchical directory-scoped nodes |
| **Sections** | Commands, Architecture, Style, Testing | Boundaries, Contracts, Rules, Ownership, Downlinks |
| **Token target** | 200-400 words (~300-600 tokens) | <1500 tokens per node, focused on actionable lines |

The paper's generation prompts (from `init_planner.py`) ask for "commands commonly used" and "high-level architecture." These are exactly the content types that hurt in our eval — `make test` is a "commonly used command" that causes a 29pp penalty, and "high-level architecture" is the narrative noise that dilutes attention.

## What we're building

Three workstreams, informed by Runs 1-6 of the AGENTbench replication:

1. **Generation quality**: Replace the current narrative-heavy AGENTS.md generation with an agent-optimized format focused on terse, operational constraints.
2. **Delivery mechanism**: Preamble injection + selective push-on-read for reliable content delivery.
3. **Eval methodology**: Paired design with McNemar's test for statistically sound comparisons.

## Why this approach

Content quality and delivery reliability are entangled — can't evaluate one without fixing the other. Three findings drive the design:

1. **Content matters more than delivery**: The `make test` confound alone explains much of intent_layer's underperformance vs none on graphiti (29pp penalty from slow test strategy).
2. **Flat context actively hurts** (graphiti: -23pp). Hierarchical mitigates (+10pp recovery) but only when coverage exists for the relevant directory.
3. **Delivery is unreliable**: Claude reads AGENTS.md sometimes (383k tokens, passes), doesn't other times (196k tokens, fails). The pull model is a coin flip.

We fix generation quality so the content is worth delivering, fix delivery so the content actually reaches Claude, and fix eval methodology so we can tell whether it worked.

## Key decisions

### Content: agent-optimized markdown (5 sections)

**Decision**: Replace the default AGENTS.md generation with terse, rule-focused markdown. Fix generation, not individual eval files.

**Rationale**: Current generation optimizes for human readers (narrative prose, architecture overviews). The primary consumer is an AI agent that needs operational constraints, not documentation. The eval data confirms: Pitfalls and Contracts sections help; Overview and Architecture sections are noise.

**Section mapping** (current → proposed):

| Current (11 sections) | Proposed (5 sections) | Notes |
|---|---|---|
| Purpose | *Dropped* | 1-line comment in heading |
| Design Rationale | *Dropped* | Narrative, not actionable |
| Code Map | *Dropped* | Agents discover this by reading |
| Public API | *Dropped* | IDEs/LSP handles better |
| Entry Points | **Ownership** | Merged: file→responsibility + entry points |
| Contracts | **Contracts** | Kept: invariants not in type system |
| Pitfalls + Patterns + Checks | **Rules** | Merged into flat imperative list |
| Boundaries (Always/Ask/Never) | **Boundaries** | Repurposed: import/dependency constraints |
| Downlinks | **Downlinks** | Kept: child node pointers |
| External Dependencies | *Dropped* | Rarely actionable for bug fixes |
| Data Flow | *Dropped* | Narrative |

**Format example**:

```markdown
# graphiti_core/utils/

## Boundaries
- Imports from: graphiti_core.models
- Does not import from: graphiti_core.server, graphiti_core.driver

## Contracts
- All datetime parameters must be UTC-normalized before comparison
- Edge lists can be empty — callers must handle zero-length

## Rules
- Filter falsey values from edge lists before iteration
- API responses can be list or dict; check isinstance before .get()
- FalkorDB returns string IDs for numeric fields
- Test with: pytest tests/unit/test_temporal.py -k test_utc

## Ownership
- temporal_utils.py: datetime normalization, timezone handling
- maintenance/: graph cleanup operations, bulk updates
- Start here for datetime bugs: temporal_utils.py

## Downlinks
| Area | Node | Description |
| maintenance | `maintenance/AGENTS.md` | Graph cleanup, bulk edge operations |
```

**Spec conformance**: Checked against https://agents.md/ — the spec requires only standard markdown with no mandatory sections. This format is fully conformant.

**Rollout**: Replace the default generation. All new AGENTS.md files use the agent-optimized format. Existing files stay as-is unless regenerated.

### New generation prompt

Replace the current 12-section exploration prompt with:

```
Analyze [DIRECTORY] for an agent-facing AGENTS.md. Return ONLY:

## Boundaries
- What this module imports from (allowed dependencies)
- What must NOT import from this module
- Any isolation rules (e.g., "modules can only import from module_utils")

## Contracts
- Invariants not enforced by the type system
- Pre/post conditions on key functions
- Data format assumptions (e.g., "datetimes must be UTC-normalized")

## Rules
- One imperative sentence per line
- Sourced from: git history (fix/revert commits), known failure modes
- Format: "[WHEN condition] [ALWAYS/NEVER] [action]" or plain imperative
- MAY include targeted test commands (e.g., "test with: pytest tests/unit/test_foo.py")
- MUST NOT include broad commands (e.g., "make test", "pytest", "npm test")

## Ownership
- Map files/directories to responsibilities
- Include "start here for [task]" entries for common operations
- Only non-obvious mappings (skip if directory name = purpose)

## Downlinks
- Child AGENTS.md files below this directory
- One row per child: | Area | Node | Description |

Constraints:
- Maximum 1500 tokens
- Every line must pass: "Would an agent fixing a bug here need this?"

GOOD output (include):
- "Normalize datetimes to UTC before comparison"
- "API responses can be list or dict — check isinstance before .get()"
- "test with: pytest tests/unit/test_temporal.py -k test_utc"
- "graphiti_core.utils imports from: graphiti_core.models only"

BAD output (never generate):
- "This module handles utility functions for the project" (obvious from dir name)
- "make test" or "npm run test" (too broad, causes slow test runs)
- "Follow PEP 8 style guidelines" (linters handle this)
- "The architecture follows a layered pattern with..." (narrative)
- "Be careful when modifying this code" (vague, not actionable)
- "This is a critical component" (significance puffery)
```

**What changes**: Modify the generation prompts in `skills/intent-layer/SKILL.md` (current exploration prompt at lines 347-394), `references/section-schema.md` (mandatory/conditional sections), and `references/templates/` (starter templates).

### Delivery: preamble + selective push

**Decision**: Use both preamble injection and selective push-on-read. Belt and suspenders.

**Preamble injection**:
- Inject nearest-ancestor's Rules + Contracts sections in the prompt
- Task/problem description FIRST, then "known pitfalls for this area:" with rules
- 1.5k token cap
- Implemented in `task_runner._build_prompt()` for the eval, potentially as a hook for the plugin

**Selective push-on-read** (partially done in commit 02f29ed):
- Only inject when covering node is a child AGENTS.md (skip root — already auto-loaded)
- Extract Rules section only (not full file)
- Fire on Read/Grep of files in the covered directory

**Eval conditions** (4 conditions to isolate effects):

| Condition | Files on disk | Preamble | Push-on-read |
|-----------|--------------|----------|--------------|
| none | No | No | No |
| flat_llm | Single CLAUDE.md | Pull instruction | No |
| intent_layer | Hierarchical AGENTS.md | Pull instruction | Yes |
| intent_layer_preamble | Hierarchical AGENTS.md | Inline rules | Yes |

### Eval: paired design with McNemar's test

**Decision**: Analyze eval data as paired comparisons, not independent samples.

**Rationale**: The eval already runs all conditions on each task. The data is structurally paired — we just haven't analyzed it that way. McNemar's test on paired binary outcomes needs far fewer samples to detect effects than unpaired comparisons.

**How it works**:
- For each (task, rep) pair, classify as concordant (both pass or both fail) or discordant (one passes, other fails)
- Test whether discordant pairs favor one condition
- 10-15 discordant pairs can reach significance (vs ~250 unpaired samples for the same effect size)

**Statistical methods**:
- **McNemar's test**: for pairwise condition comparisons (paired binary outcomes)
- **Wilson score CIs**: for per-condition pass rates (correct at any N, unlike CLT)
- **Fisher's exact test**: for unpooled comparisons when pairing isn't possible
- Drop CLT-based normal approximation CIs (systematically too tight at N<100)

**Repos**: Focus on graphiti (strongest differential signal) + ansible (star result). Drop pdm (near-ceiling, context adds noise).

**Rep count**: 5 minimum, 10 for clean final run.

## What the paper actually tests (from eth-sri/agentbench source)

The paper's `init_planner.py` has four generation prompts:

| Agent | Prompt focus | Word target |
|---|---|---|
| Claude Code (`_CLAUDE_CODE_INIT_PROMPT`) | Commands + architecture | No limit |
| Codex (`_CODEX_INIT_PROMPT`) | Structure, commands, style, testing, commits | 200-400 words |
| Qwen (`_QWEN_INIT_PROMPT`) | Explore 10 files, write overview + commands + conventions | No limit |
| Gemini (`_GEMINI_INIT_PROMPT`) | Same as Qwen but for Gemini | No limit |

Key detail: the paper writes the **same content** to both `AGENTS.md` AND `CLAUDE.md` (`env.execute(f'echo ... > AGENTS.md')` then `env.execute(f'echo ... > CLAUDE.md')`). It never tests hierarchical context — just one flat file duplicated.

The `human_planner.py` finds existing AGENTS.md/CLAUDE.md from the repo's git history (looking forward from the pre-fix commit). This is the "human" condition — whatever context the repo's actual maintainers wrote.

None of the prompts ask for: pitfalls, module boundaries, invariants, or failure modes. The paper tests "onboarding docs for agents" and finds they don't help. We test "operational constraints for agents" — a question nobody has answered.

## What this does NOT include

- YAML or machine-parseable AGENTS.md format (over-engineering; plain markdown is enough)
- Smart rule-level filtering/matching (over-engineering; whole-file/section injection is simpler)
- Task-type-aware generation (failing_test vs commit_message variants — not enough data yet)
- New eval repos beyond graphiti + ansible (later, once methodology is clean)
- Manually patching eval AGENTS.md files — fix generation instead

## McNemar's analysis of Run 3 data

Re-analyzed Run 3 (27 tasks × 3 conditions × 3 reps = 243 items) using paired McNemar's test. This answers the open question of whether we have enough discordant pairs.

### Data quality: 55% zero-work runs

134 of 243 runs (55%) had `wall_clock=0, tool_calls=0` — the agent did zero work. Of these, 66 were marked success (pre-validation pass or cache hit) and 68 were marked fail (infra error). This inflates denominators and hides real signal. Fixing data quality is a prerequisite for any meaningful eval.

### Overall results (all repos pooled)

81 (task, rep) pairs analyzed across 3 pairwise comparisons:

| Comparison | Discordant pairs | Winner | p-value (exact binomial) |
|---|---|---|---|
| **flat_llm vs none** | 17 | none wins 13/17 | **p=0.049** |
| **intent_layer vs none** | 17 | none wins 11/17 | p=0.332 |
| **intent_layer vs flat_llm** | 18 | IL wins 12/18 | p=0.238 |

**Flat context significantly hurts** — this replicates the paper's core finding with a proper paired test on our small dataset. None wins 76% of discordant pairs against flat_llm.

Intent Layer vs none is not significant. We have 17 discordant pairs with an 11:6 split favoring none. Need ~25+ discordant pairs to detect a real effect at 80% power.

### Per-repo breakdown

**graphiti** (10 tasks × 3 reps = 30 pairs):
- flat_llm vs none: 10 discordant, none wins 8/10, **p=0.039**
- intent_layer vs none: 8 discordant, none wins 6/8, p=0.145
- intent_layer vs flat_llm: 8 discordant, IL wins 6/8, p=0.145

Graphiti is where flat hurts most. Intent Layer recovers some damage but doesn't fully overcome the baseline.

**ansible** (10 tasks × 3 reps = 30 pairs):
- flat_llm vs none: 3 discordant, none wins 2/3, p=0.500
- intent_layer vs none: 4 discordant, IL wins 4/4, **p=0.125**
- intent_layer vs flat_llm: 5 discordant, IL wins 4/5, p=0.188

Ansible shows the strongest IL signal — IL wins 4/4 discordant pairs vs none. Not significant at p<0.05, but the direction is clear. The star result (fix-ansiblemodule-human-to-bytes: none 0/3, flat 1/3, intent 3/3) drives this.

**pdm** (7 tasks × 3 reps = 21 pairs):
- Near-ceiling performance across all conditions. Few discordant pairs, no signal.

### What this means for next runs

1. **Flat hurting is confirmed** (p=0.049). The paper's finding replicates. This validates our hypothesis that content type matters.
2. **Intent Layer signal is directional but underpowered.** 17 discordant pairs isn't enough. Need 5+ reps on graphiti + ansible to get ~25 discordant pairs.
3. **Data quality is the bottleneck.** 55% zero-work runs mean we're throwing away over half our compute. Fix infra errors before adding reps.
4. **graphiti is the right repo to focus on.** Strongest differential signal, clear flat-hurts pattern, and coverage gaps we can fill.

## Open questions

- How to handle generation for directories where we have no failure data? Rules section would be empty. Fall back to Contracts + Boundaries only?
- Should the preamble include Ownership alongside Rules + Contracts? Ownership helps navigation but increases token count.
- Should we run the paper's eval harness (`eth-sri/agentbench`) directly for comparison, or stick with our own?
- For the "human" condition: should we hand-write AGENTS.md in the new format, or test generation quality only?

## Next steps

→ `/workflows:plan` for implementation across all three workstreams
