---
name: intent-layer
description: >
  Set up hierarchical Intent Layer (AGENTS.md files) for codebases.
  Use when initializing a new project, adding context infrastructure to an existing repo,
  user asks to set up AGENTS.md, add intent layer, make agents understand the codebase,
  or scaffolding AI-friendly project documentation.
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
