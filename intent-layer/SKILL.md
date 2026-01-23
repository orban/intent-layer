---
name: intent-layer
description: >
  Set up hierarchical Intent Layer (AGENTS.md files) for codebases.
  Use when initializing a new project, adding context infrastructure to an existing repo,
  user asks to set up AGENTS.md, add intent layer, make agents understand the codebase,
  or scaffolding AI-friendly project documentation.
argument-hint: "[/path/to/project]"
---

# Intent Layer

> **TL;DR**: Create CLAUDE.md/AGENTS.md files that help AI agents navigate your codebase like senior engineers. Run `detect_state.sh` first to see what's needed.

Hierarchical AGENTS.md infrastructure so agents navigate codebases like senior engineers.

---

## Sub-Skills

This skill includes specialized sub-skills that are **automatically invoked** when appropriate:

| Sub-Skill | Location | Auto-Invoke When |
|-----------|----------|------------------|
| `git-history` | `git-history/SKILL.md` | Creating nodes for existing code (extracts pitfalls from commits) |
| `pr-review-mining` | `pr-review-mining/SKILL.md` | Creating nodes for existing code (extracts pitfalls from PR discussions) |
| `pr-review` | `pr-review/SKILL.md` | Reviewing PRs that touch Intent Layer nodes |

### git-history (Auto-Invoked During Setup)

When creating nodes for directories with git history, **automatically run git-history analysis** to pre-populate:
- **Pitfalls** from bug fix commits
- **Anti-patterns** from revert commits
- **Architecture Decisions** from refactor commits
- **Contracts** from breaking change commits

```
Trigger: Creating AGENTS.md for directory with >50 commits
Action: Run git-history analysis before writing node
```

### pr-review-mining (Auto-Invoked During Setup)

When creating nodes for directories with merged PRs, **automatically run PR mining** to pre-populate:
- **Pitfalls** from PR Risks sections and review warnings
- **Contracts** from Breaking Changes sections
- **Architecture Decisions** from Why sections and Alternatives Considered
- **Anti-patterns** from rejected approaches in reviews

```
Trigger: Creating AGENTS.md for directory with merged PRs
Action: Run pr-review-mining alongside git-history, merge findings
```

### pr-review (Auto-Invoked for PRs)

When reviewing PRs that modify code covered by Intent Layer:
- Verify contracts are respected
- Check pitfalls are avoided
- Flag potential Intent Layer updates needed

```
Trigger: PR touches files under an AGENTS.md
Action: Run pr-review with --ai-generated if applicable
```

---

## Quick Start

### Step 0: Check State

```bash
scripts/detect_state.sh /path/to/project
```

| State | Action |
|-------|--------|
| `none` | Create root file (continue below) |
| `partial` | Add Intent Layer section to existing root |
| `complete` | Use `intent-layer-maintenance` skill instead |

### Step 1: Measure

```bash
# Auto-discover all candidate directories
scripts/estimate_all_candidates.sh /path/to/project

# Or analyze structure first
scripts/analyze_structure.sh /path/to/project
```

### Step 2: Create Root Node

Choose CLAUDE.md (Anthropic) or AGENTS.md (cross-tool). Pick template by size:
- **Small** (<50k tokens): `references/templates.md` → Small Project
- **Medium** (50-150k): `references/templates.md` → Medium Project
- **Large** (>150k/monorepo): `references/templates.md` → Large Project

### Step 3: Create Child Nodes (if needed)

| Signal | Action |
|--------|--------|
| Directory >20k tokens | Create `AGENTS.md` |
| Responsibility shift | Create `AGENTS.md` |
| Cross-cutting concern | Document at nearest common ancestor |

Use child template from `references/templates.md`.

### Step 4: Validate

```bash
scripts/validate_node.sh CLAUDE.md
scripts/validate_node.sh path/to/AGENTS.md
```

Checks: token count <4k, required sections, no absolute paths, no TODOs.

### Step 5: Cross-Tool Compatibility

```bash
ln -s CLAUDE.md AGENTS.md  # If CLAUDE.md is primary
```

---

## Interactive Wizard

Step-by-step guided setup with prompts at each decision point.

### Step 1: Detect State

Run `scripts/detect_state.sh`, then based on result:

| State | Action |
|-------|--------|
| `none` | Ask user: "Create CLAUDE.md or AGENTS.md as root?" |
| `partial` | Ask user: "What's the one-line TL;DR for this project?" |
| `complete` | Redirect to `intent-layer-maintenance` skill |

### Step 2: Measure & Decide

Run `scripts/estimate_all_candidates.sh`, then:
- Present candidates table to user
- Ask: "Which directories should get their own AGENTS.md?"

### Step 3: Mine History (Auto-Invoked)

**Before creating each node**, automatically analyze both git history AND PR discussions using the mining scripts:

```bash
# Git commit analysis (extracts pitfalls, anti-patterns, decisions, contracts)
~/.claude/skills/intent-layer/scripts/mine_git_history.sh [directory]

# GitHub PR analysis (requires gh CLI)
~/.claude/skills/intent-layer/scripts/mine_pr_reviews.sh --limit 50

# Check for stale nodes (during maintenance)
~/.claude/skills/intent-layer/scripts/detect_staleness.sh --code-changes [directory]
```

**mine_git_history.sh** extracts from commits:
1. Bug fixes → Pre-populate Pitfalls
2. Reverts → Pre-populate Anti-patterns
3. Refactors → Pre-populate Architecture Decisions
4. Breaking changes → Pre-populate Contracts

**mine_pr_reviews.sh** extracts from PRs:
1. Risks sections → Pre-populate Pitfalls
2. Review warnings → Pre-populate Pitfalls
3. Breaking Changes → Pre-populate Contracts
4. Why/Alternatives → Pre-populate Architecture Decisions

Present merged findings to user: "History suggests these pitfalls: [list]. Include them?"

### Step 4: Create Nodes

For root node:
- Ask user about project purpose
- Select template by size (Small/Medium/Large from `references/templates.md`)
- **Include git-history findings** in appropriate sections

For each child node:
- Ask user about directory's responsibility
- Use child template from `references/templates.md`
- **Include git-history findings** for that directory

### Step 4b: Add Pre-flight Checks

For directories with history of mistakes or complex operations:

**Ask**: "What operations in this directory have caused problems before?"

For each risky operation identified:
1. Ask: "What would you check before doing [operation]?"
2. Convert answer to verifiable check format
3. Add to Pre-flight Checks section

**Mine from history**:
```bash
# Find reverts and fixes that suggest missing checks
~/.claude/skills/intent-layer/scripts/mine_git_history.sh [directory] | grep -i "fix\|revert"
```

Present findings: "These commits suggest potential checks: [list]. Add any?"

### Step 5: Validate

Run `scripts/validate_node.sh` on all created nodes:
- Show validation results
- Offer to fix warnings/errors

### Step 6: Symlink

Ask user: "Create symlink for cross-tool compatibility? (AGENTS.md → CLAUDE.md)"

If yes: `ln -s CLAUDE.md AGENTS.md`

---

## Parallel Setup (Large Codebases)

For codebases >200k tokens, use parallel subagents to dramatically speed up exploration.

### When to Use Parallel Mode

| Codebase Size | Approach |
|---------------|----------|
| <100k tokens | Sequential (standard workflow) |
| 100-500k tokens | Parallel exploration, sequential synthesis |
| >500k tokens | Full parallel mode (explore + validate) |

### Step 1: Identify Subsystems

Run structure analysis first:
```bash
scripts/analyze_structure.sh /path/to/project
```

Identify 3-6 major subsystems from the output (e.g., `src/api/`, `src/core/`, `src/db/`).

### Step 2: Parallel Exploration + History Mining

Spawn subagents for **code exploration, git history, AND PR mining** in parallel:

```
# Code exploration (one per subsystem)
Task 1: "Analyze src/api/ for Intent Layer setup. Find: contracts/invariants,
         entry points for common tasks, pitfalls/surprising behaviors,
         patterns that must be followed. Return structured findings."

Task 2: "Analyze src/core/ for Intent Layer setup. Find: contracts/invariants,
         entry points for common tasks, pitfalls/surprising behaviors,
         patterns that must be followed. Return structured findings."

Task 3: "Analyze src/db/ for Intent Layer setup. Find: contracts/invariants,
         entry points for common tasks, pitfalls/surprising behaviors,
         patterns that must be followed. Return structured findings."

# Git history analysis (parallel with exploration)
Task 4: "Run git-history analysis on src/api/. Find bug fixes, reverts,
         refactors, and breaking changes. Return as Intent Layer findings."

Task 5: "Run git-history analysis on src/core/. Find bug fixes, reverts,
         refactors, and breaking changes. Return as Intent Layer findings."

Task 6: "Run git-history analysis on src/db/. Find bug fixes, reverts,
         refactors, and breaking changes. Return as Intent Layer findings."

# PR review mining (parallel with above)
Task 7: "Run pr-review-mining on src/api/. Extract from PR descriptions
         and review comments: pitfalls, contracts, architecture decisions.
         Return as Intent Layer findings with PR numbers."

Task 8: "Run pr-review-mining on src/core/. Extract from PR descriptions
         and review comments: pitfalls, contracts, architecture decisions.
         Return as Intent Layer findings with PR numbers."

Task 9: "Run pr-review-mining on src/db/. Extract from PR descriptions
         and review comments: pitfalls, contracts, architecture decisions.
         Return as Intent Layer findings with PR numbers."
```

**Critical**: Launch all agents in parallel (single message with multiple Task calls).

### Step 3: Synthesize Results

Once all agents complete:
1. **Merge code exploration + git history + PR mining** findings per subsystem
2. Identify cross-cutting concerns (appear in multiple findings)
3. Place cross-cutting items in root node
4. Create child AGENTS.md for each subsystem with:
   - Code-derived contracts and entry points
   - Git-history-derived pitfalls and architecture decisions
   - PR-mining-derived pitfalls, contracts, and rationale
5. **Deduplicate** where multiple sources found the same insight
6. **Prefer PR-sourced rationale** when available (richer "why" context)

### Step 4: Parallel Validation

Validate all nodes in parallel:
```
Task 1: "Run validate_node.sh on CLAUDE.md, report results"
Task 2: "Run validate_node.sh on src/api/AGENTS.md, report results"
Task 3: "Run validate_node.sh on src/core/AGENTS.md, report results"
```

### Example Parallel Exploration Prompt

For each subsystem, use this structured prompt:

```markdown
Explore [DIRECTORY] for Intent Layer documentation. Return:

## Contracts & Invariants
- What must always be true?
- What dependencies exist?

## Entry Points
| Task | Start Here |
|------|------------|
| [common task] | [file] |

## Pitfalls
- What surprises newcomers?
- What looks wrong but isn't?

## Patterns
- Required patterns for new code
- Anti-patterns to avoid

Keep findings specific to this directory. Note cross-cutting concerns separately.
```

### Parallel Mode Benefits

| Metric | Sequential | Parallel |
|--------|------------|----------|
| 500k token codebase | ~30 min | ~10 min |
| 1M+ token codebase | ~60 min | ~15 min |
| Subsystem coverage | Variable | Consistent |

---

## Spec-First Workflow (Greenfield)

For projects WITHOUT existing code. Write Intent Nodes as specs, then scaffold.

### Step 1: Define Scope
- What's the project vision?
- What are the major planned subsystems?
- Who are the stakeholders?

### Step 2: Create Spec Root
Use "Spec Root Template" from `references/templates.md`:
- Vision statement (not TL;DR of existing code)
- Planned Subsystems (not discovered from code)
- Design Constraints (not extracted contracts)
- Implementation Targets (where to build first)

### Step 3: Create Component Specs
For each planned subsystem, create AGENTS.md with:
- Responsibility Charter (what it will own)
- Interface Contracts (how others will call it)
- Acceptance Criteria (how we know it's done)

### Step 4: AI Scaffolding
Ask Claude to scaffold against the specs:
- "Create directory structure matching the Planned Subsystems"
- "Generate interface stubs for the contracts defined"
- "Set up test fixtures based on acceptance criteria"

### Step 5: Implementation Loop
Build incrementally:
1. Implement against spec
2. Update spec as requirements clarify
3. Spec nodes evolve into documentation nodes

### Step 6: Transition to Maintenance
When implementation complete:
- Fill in discovered Pitfalls
- Add actual Entry Points
- Run `validate_node.sh` and transition to maintenance skill

---

## Concepts

<details>
<summary><strong>Why Intent Layers?</strong> (click to expand)</summary>

### The Problem
AI agents reading raw code lack the tribal knowledge that experienced engineers have:
- Where to start for common tasks
- What patterns are expected
- What invariants must never be violated
- What pitfalls to avoid

### The Solution
Intent Nodes (CLAUDE.md/AGENTS.md files) provide compressed, high-signal context that tells agents *what matters* without reading thousands of lines of code.

### How It Works
- **Ancestor-based loading**: Reading a child node auto-loads all ancestors (T-shaped knowledge)
- **Progressive disclosure**: Start minimal, agents drill down when needed
- **Compression**: 200k tokens of code → 2k token node (100:1 ratio)

</details>

<details>
<summary><strong>Core Rules</strong> (click to expand)</summary>

### One Root Only
CLAUDE.md and AGENTS.md should NOT coexist at project root. Pick one and symlink the other for cross-tool compatibility.

### Child Nodes Named AGENTS.md
Subdirectory nodes should be `AGENTS.md` (not CLAUDE.md) for cross-tool compatibility.

### Token Budgets
- Each node: <4k tokens (prefer <3k)
- Target 100:1 compression
- If you can't compress, scope is too broad → split

### What to Document
Keep: contracts, invariants, surprising behaviors, entry points, non-obvious patterns
Delete: tech stack lists, standard patterns, obvious file purposes

</details>

<details>
<summary><strong>Effort Estimates</strong> (click to expand)</summary>

| Codebase Size | Experienced | Newcomer |
|---------------|-------------|----------|
| <50k tokens | 1-2 hours | 3-5 hours |
| 50-150k tokens | 3-5 hours | 6-10 hours |
| >150k tokens | 5-10 hours | 10-20 hours |

Budget additional time for SME interviews—tribal knowledge takes conversation to extract.

</details>

---

## Resources

### Scripts

| Script | Purpose |
|--------|---------|
| `detect_state.sh` | Check Intent Layer state (none/partial/complete) |
| `analyze_structure.sh` | Find semantic boundaries |
| `estimate_tokens.sh` | Measure single directory |
| `estimate_all_candidates.sh` | Measure all candidates at once |
| `validate_node.sh` | Check node quality before committing |
| `capture_pain_points.sh` | Generate maintenance capture template |
| `detect_changes.sh` | Find affected nodes on merge/PR |
| `show_status.sh` | Health dashboard with metrics and recommendations |
| `show_hierarchy.sh` | Visual tree display of all nodes |
| `review_pr.sh` | Review PR against Intent Layer |
| `capture_mistake.sh` | Generate mistake report for check extraction |

### Sub-Skills

| Sub-Skill | Location | Purpose |
|-----------|----------|---------|
| `git-history` | `git-history/SKILL.md` | Extract pitfalls/contracts from commit history |
| `pr-review-mining` | `pr-review-mining/SKILL.md` | Extract pitfalls/contracts from PR discussions |
| `pr-review` | `pr-review/SKILL.md` | Review PRs against Intent Layer contracts |

### References

| File | Purpose |
|------|---------|
| `templates.md` | Root (S/M/L) and child templates, three-tier boundaries |
| `node-examples.md` | Real-world examples |
| `capture-protocol.md` | SME interview questions |
| `compression-techniques.md` | How to achieve 100:1 compression, LCA placement |
| `agent-feedback-protocol.md` | Continuous improvement loop |

---

## Capture Questions

> **TL;DR**: Ask these when documenting existing code.

1. What does this area own? What's explicitly out of scope?
2. What invariants must never be violated?
3. What repeatedly confuses new engineers?
4. What patterns should always be followed?
5. What operations require extra care? What do you verify before doing them?
6. What mistakes have happened before? What check would have caught them?

For full protocol: `references/capture-protocol.md`

---

## When to Create Child Nodes

> **TL;DR**: >20k tokens or responsibility shift → create. Simple utilities → don't.

| Signal | Action |
|--------|--------|
| >20k tokens in directory | Create AGENTS.md |
| Responsibility shift (different owner/concern) | Create AGENTS.md |
| Hidden contracts/invariants | Document in nearest ancestor |
| Cross-cutting concern | Place at lowest common ancestor |

**Do NOT create for**: every directory, simple utilities, test folders (unless complex).

---

## Pre-flight Checks

> **TL;DR**: Testable verifications before risky operations. Add when mistakes reveal missing checks.

### What They Are

Pre-flight checks are **verifiable assertions** an agent runs before modifying code. They catch "I thought I understood" mistakes.

### When to Add

| Signal | Action |
|--------|--------|
| Mistake happened | Write check that would have caught it |
| PR reviewer flagged missing step | Convert to check |
| Complex multi-step operation | Add checks for each step |
| Critical/irreversible operation | Add comprehension + human gate |

### When NOT to Add

- Every operation (over-checking slows agents down)
- Things covered by Boundaries section (use Always/Never instead)
- Awareness-only items (use Pitfalls instead)

### Format

See `references/templates.md` → Writing Pre-flight Checks for the standard format.

### Mining Checks from History

```bash
# Find commits suggesting missing verifications
scripts/mine_git_history.sh --since "6 months ago" [directory] | grep -E "fix|broke|forgot"
```

Look for patterns like "forgot to update X" or "broke Y because didn't check Z".

---

## Capture Order (Leaf-First)

> **TL;DR**: Start at leaves, work up to root. Clarity compounds upward.

Always capture leaf-first, easy-to-hard:

1. **Start with deepest directories** (most concrete)
   - Leaf nodes compress raw code—patterns are visible
   - Easier to identify contracts when you see the implementation

2. **Work up to parent nodes** (summarize children)
   - Parent nodes compress children's Intent Nodes, not raw code
   - Wait until children are stable before writing parent

3. **Finish with root** (summarize entire hierarchy)
   - Root references child nodes, provides navigation
   - Global invariants emerge from seeing all children

**Why this order?**
- Clarity compounds upward—parent nodes reference stable children
- Avoids rewriting parents when children change
- Natural: understand details before summarizing

**Anti-pattern**: Starting at root and working down leads to vague descriptions that need constant revision as you discover what's actually in the code.

---

## Feedback Flywheel

> **TL;DR**: Agents surface missing context during work → humans review → Intent Layer improves → future agents start better.

### Continuous Improvement Loop

```
Agent works → Finds gap → Surfaces finding → Human reviews → Node updated → Future agents benefit
```

### During Normal Work

When you encounter gaps while working, surface them using the format in `references/agent-feedback-protocol.md`:

```markdown
### Intent Layer Feedback
| Type | Location | Finding |
|------|----------|---------|
| Missing pitfall | `src/api/AGENTS.md` | Rate limiter fails silently when Redis down |
```

### On Merge/PR

Run change detection to identify which nodes need review:

```bash
scripts/detect_changes.sh main HEAD
```

This outputs affected nodes in leaf-first order for systematic review.

### Full Protocol

See `references/agent-feedback-protocol.md` for:
- When to surface findings
- Structured feedback format
- Human review workflow (Accept/Reject/Defer)

### Mistake → Check Pipeline

When agents surface mistakes, evaluate for check conversion:

```
Mistake surfaced → "Would a check have caught this?"
                            │
              ┌─────────────┴─────────────┐
              │                           │
             Yes                          No
              │                           │
              ▼                           ▼
    Write Pre-flight Check         Add to Pitfalls
              │                    (awareness only)
              ▼
    Add to AGENTS.md Pre-flight section
```

**Check conversion template**:
```markdown
Mistake: [What happened]
Operation: [What agent was doing]
Check: Before [operation] → [verification that would have caught it]
```

Use `scripts/capture_mistake.sh` to generate structured mistake reports.

---

## Maintenance Flywheel

> **TL;DR**: Update nodes when behavior changes, not just when code changes.

When files change (e.g., on merge):

1. **Identify affected nodes** - Run `scripts/detect_changes.sh base head`
2. **Check behavior change** - Did contracts/invariants change, or just formatting?
3. **Update if needed** - Behavior change → update affected node
4. **Consider new nodes** - Patterns emerging → new node or LCA update?

For full maintenance workflow, use: **`intent-layer-maintenance`** skill

---

## What's Next?

After completing initial setup (state = `complete`):

### Immediate Actions
1. Create symlink for cross-tool compatibility
2. Test by asking an AI agent to perform a common task
3. Share with team (note in README or onboarding docs)

### Ongoing Maintenance
| Trigger | Action |
|---------|--------|
| Quarterly | Run `intent-layer-maintenance` skill |
| Post-incident | Update Pitfalls + Contracts |
| After refactor | Update Entry Points + Subsystem Boundaries |
| After new feature | Update Architecture Decisions + Patterns |
| **PR Review** | **Auto-invoke `pr-review` sub-skill** |

### PR Review Integration (Auto-Invoked)

When reviewing PRs that touch files covered by Intent Layer nodes:

```bash
# Automatically run pr-review
scripts/review_pr.sh main HEAD --ai-generated
```

The `pr-review` sub-skill will:
- Check PR against contracts in relevant AGENTS.md
- Flag if PR approaches documented pitfalls
- Suggest Intent Layer updates if contracts changed

### Optional: CI Integration

```yaml
- name: Check Intent Layer
  run: ~/.claude/skills/intent-layer/scripts/detect_state.sh .

- name: PR Review (if Intent Layer exists)
  if: github.event_name == 'pull_request'
  run: |
    ~/.claude/skills/intent-layer/scripts/review_pr.sh origin/main HEAD --exit-code
```

### Related Skills
| Skill | Use When |
|-------|----------|
| `intent-layer-maintenance` | Quarterly audits, post-incident updates |
| `intent-layer-query` | Asking questions about the codebase |
| `intent-layer-onboarding` | Orienting newcomers |
| `git-history` (sub-skill) | Mining commit history for insights |
| `pr-review-mining` (sub-skill) | Mining PR discussions for insights |
| `pr-review` (sub-skill) | Reviewing PRs against Intent Layer |
