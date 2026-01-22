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

### Step 3: Create Nodes

For root node:
- Ask user about project purpose
- Select template by size (Small/Medium/Large from `references/templates.md`)

For each child node:
- Ask user about directory's responsibility
- Use child template from `references/templates.md`

### Step 4: Validate

Run `scripts/validate_node.sh` on all created nodes:
- Show validation results
- Offer to fix warnings/errors

### Step 5: Symlink

Ask user: "Create symlink for cross-tool compatibility? (AGENTS.md → CLAUDE.md)"

If yes: `ln -s CLAUDE.md AGENTS.md`

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

### Optional: CI Integration

```yaml
- name: Check Intent Layer
  run: ~/.claude/skills/intent-layer/scripts/detect_state.sh .
```

### Next Skill
When ready for maintenance: **`intent-layer-maintenance`**
