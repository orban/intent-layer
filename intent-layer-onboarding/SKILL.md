---
name: intent-layer-onboarding
description: >
  Get oriented in an unfamiliar codebase using its Intent Layer.
  Use when joining a new project, exploring a codebase for the first time,
  or helping someone understand "where do I start?" questions.
argument-hint: "[/path/to/project] [--role <role>] [--task <first-task>]"
---

# Intent Layer Onboarding

Use an existing Intent Layer to quickly orient yourself (or a new team member) in a codebase.

## Prerequisites

- Project must have Intent Layer state = `complete`
- Run `intent-layer` skill first if state is `none` or `partial`

## Quick Start

```bash
# Check Intent Layer exists
~/.claude/skills/intent-layer/scripts/detect_state.sh /path/to/project

# Generate orientation overview
scripts/generate_orientation.sh /path/to/project

# View hierarchy
~/.claude/skills/intent-layer/scripts/show_hierarchy.sh /path/to/project
```

---

## The 15-Minute Orientation

Get productive in a new codebase in 15 minutes using this workflow.

### Step 1: Read the Root (2 min)

Read the root CLAUDE.md or AGENTS.md completely. Focus on:

- **TL;DR** - One sentence project purpose
- **Subsystem Boundaries** - Major areas and owners
- **Contracts** - Global rules that apply everywhere
- **Pitfalls** - Surprises that bite newcomers

```bash
# Find and display root node
cat /path/to/project/CLAUDE.md || cat /path/to/project/AGENTS.md
```

### Step 2: Map the Hierarchy (2 min)

Visualize the full Intent Layer structure:

```bash
~/.claude/skills/intent-layer/scripts/show_hierarchy.sh /path/to/project
```

Note:
- How many child nodes exist
- Which areas have the most documentation (complexity signals)
- Depth of hierarchy (shallow = simple, deep = complex)

### Step 3: Identify Your Entry Point (3 min)

Based on your role or first task, find where to start:

| If your role is... | Start with... |
|-------------------|---------------|
| Frontend engineer | UI/components AGENTS.md |
| Backend engineer | API/services AGENTS.md |
| DevOps/Platform | Infrastructure AGENTS.md |
| Full-stack | Root node + busiest subsystem |

| If your first task is... | Find... |
|-------------------------|---------|
| Bug fix in area X | AGENTS.md closest to X |
| New feature | Entry Points in relevant subsystem |
| Understanding flow | Root → follow data path |

### Step 4: Deep-Read Your Area (5 min)

For your identified entry point:

1. Read the specific AGENTS.md completely
2. Note the **Entry Points** - these are your starting files
3. Note the **Contracts** - rules you must follow
4. Note the **Pitfalls** - traps to avoid

### Step 5: Verify Understanding (3 min)

Test your mental model:

1. Can you explain the project in one sentence?
2. Do you know where your first change goes?
3. Do you know what rules apply to that area?
4. Do you know what NOT to do?

If any answer is "no", re-read the relevant node.

---

## Role-Based Onboarding

### For AI Agents

When an AI agent needs to understand a new codebase:

**Minimum context load:**
1. Root node (always)
2. Node for target area (if known)
3. Ancestors of target (for inherited constraints)

**Query pattern:**
```
"I need to [task] in [area]. What should I know?"
```

**Response pattern:**
```markdown
## Context for [task]

### Relevant Node
`path/to/AGENTS.md`

### Key Constraints
- [From local node]
- [Inherited from ancestors]

### Entry Point
Start at: `path/to/file.ts`

### Watch Out For
- [Pitfall 1]
- [Pitfall 2]
```

### For New Engineers

When a human is joining the team:

**Day 1 Goals:**
1. Understand project purpose (root TL;DR)
2. Know major subsystems (root Subsystem Boundaries)
3. Know global rules (root Contracts)
4. Know what surprises exist (root Pitfalls)

**Week 1 Goals:**
1. Deep-read your team's AGENTS.md files
2. Understand your area's specific contracts
3. Successfully complete one small task
4. Know where to ask questions

**Onboarding Checklist:**
```markdown
## Onboarding Checklist: [Name]

### Day 1
- [ ] Read root CLAUDE.md/AGENTS.md
- [ ] Run show_hierarchy.sh to see structure
- [ ] Identify which subsystem I'll work in
- [ ] Read my subsystem's AGENTS.md

### Week 1
- [ ] Complete first small task
- [ ] Verify I followed all contracts
- [ ] Note any confusion for Intent Layer feedback
- [ ] Ask about anything not documented
```

### For Code Reviewers

When reviewing code in an unfamiliar area:

1. Find AGENTS.md for the changed files
2. Check Contracts section - are they followed?
3. Check Pitfalls section - are they avoided?
4. Check Anti-patterns section - none introduced?

---

## Task-Based Onboarding

### "I need to fix a bug in X"

**Workflow:**
1. Find AGENTS.md nearest to X
2. Read Pitfalls (often explains the bug)
3. Read Contracts (constraints on the fix)
4. Find Entry Point for debugging

**Output:**
```markdown
## Bug Fix Context: [area]

**Relevant Node:** `path/to/AGENTS.md`

**Common Pitfalls (check these first):**
- [Pitfall that might explain bug]

**Fix Constraints:**
- [Rules the fix must follow]

**Start Debugging At:**
- `path/to/entry/file.ts`
```

### "I need to add a feature to Y"

**Workflow:**
1. Find AGENTS.md for Y
2. Check if feature is in scope (vs out of scope)
3. Read Entry Points for "add new..."
4. Read Contracts for implementation rules
5. Check parent nodes for inherited constraints

**Output:**
```markdown
## Feature Context: [feature] in [area]

**In Scope:** Yes/No (from AGENTS.md)

**Entry Point:**
- Start at: `path/to/file.ts`
- Pattern to follow: [from Entry Points]

**Constraints:**
- [Local rules]
- [Inherited rules]

**Related Areas:**
- [Siblings that might be affected]
```

### "I need to understand how Z works"

**Workflow:**
1. Find AGENTS.md that owns Z
2. Read TL;DR for high-level understanding
3. Read Architecture Decisions for rationale
4. Follow Entry Points to key files
5. Read ancestors for broader context

**Output:**
```markdown
## Understanding: [Z]

**Owner:** `path/to/AGENTS.md`

**TL;DR:**
> [From node]

**Why It's Designed This Way:**
- [From Architecture Decisions]

**Key Files to Read:**
1. `file1.ts` - [purpose]
2. `file2.ts` - [purpose]

**Broader Context:**
- [From parent nodes]
```

---

## Generating Orientation Documents

For teams that want a static onboarding doc:

### Quick Overview

```bash
scripts/generate_orientation.sh /path/to/project --format overview
```

Produces:
- Project summary
- Subsystem map
- Global rules
- Common tasks entry points

### Full Onboarding Guide

```bash
scripts/generate_orientation.sh /path/to/project --format full
```

Produces:
- Everything in overview
- Per-subsystem deep dives
- Role-based entry points
- First-week checklist

### Team-Specific

```bash
scripts/generate_orientation.sh /path/to/project --role backend
```

Produces:
- Filtered view for backend engineers
- Relevant subsystems only
- Backend-specific entry points

---

## Interactive Onboarding Session

For a guided, interactive orientation:

### Step 1: Gather Context

Ask the newcomer:
1. What's your role? (frontend/backend/fullstack/devops/other)
2. What's your first task? (if known)
3. What's your experience level? (junior/mid/senior)

### Step 2: Generate Personalized Path

Based on answers, create a reading list:

**Junior + No specific task:**
```markdown
## Your Onboarding Path

1. **Start Here:** CLAUDE.md (root) - 10 min read
2. **Then:** [area matching role]/AGENTS.md - 5 min read
3. **Exercise:** Find where [simple task] would be done
4. **Verify:** Explain the project back to me
```

**Senior + Specific task:**
```markdown
## Your Onboarding Path

1. **Quick Scan:** CLAUDE.md TL;DR + Subsystems - 2 min
2. **Deep Read:** [task area]/AGENTS.md - 5 min
3. **Context:** Walk ancestors for inherited rules - 3 min
4. **Start:** [Entry point for task]
```

### Step 3: Verify Understanding

After they complete the path, ask:
1. "What does this project do in one sentence?"
2. "Where would you make your first change?"
3. "What rules must you follow there?"
4. "What mistakes should you avoid?"

If answers are weak, point them to specific sections.

### Step 4: Capture Gaps

If they found the Intent Layer confusing or incomplete:

```markdown
### Intent Layer Feedback

| Type | Location | Finding |
|------|----------|---------|
| Unclear | `src/api/AGENTS.md` | Entry Points don't explain X |
| Missing | `CLAUDE.md` | No mention of Y subsystem |
```

Feed this back via `intent-layer-maintenance` skill.

---

## Common Questions

### "Where do I start?"

1. Run `show_hierarchy.sh` to see structure
2. Read root node for project overview
3. Identify your area from Subsystem Boundaries
4. Read that area's AGENTS.md
5. Follow its Entry Points

### "What can I safely change?"

1. Find AGENTS.md for the area
2. Check **Contracts** - these are invariants
3. Check **Anti-patterns** - don't introduce these
4. Anything not constrained is fair game

### "Who owns this code?"

1. Find nearest AGENTS.md (walk up if needed)
2. Check TL;DR for ownership statement
3. Check Subsystem Boundaries in parent for team info

### "Why is it done this way?"

1. Find AGENTS.md for the area
2. Check **Architecture Decisions** section
3. Follow any ADR links
4. If not documented, flag as feedback

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `generate_orientation.sh` | Create onboarding documents |
| `show_hierarchy.sh` | Visualize Intent Layer structure |
| `show_status.sh` | Check Intent Layer health |
| `query_intent.sh` | Search for specific concepts |
| `walk_ancestors.sh` | Gather context from hierarchy |

Scripts from intent-layer: `~/.claude/skills/intent-layer/scripts/`
Scripts from intent-layer-query: `~/.claude/skills/intent-layer-query/scripts/`

---

## Anti-Patterns

| Don't Do This | Do This Instead |
|--------------|-----------------|
| Skip root, jump to code | Always read root first |
| Read all nodes exhaustively | Read root + your area |
| Ignore Pitfalls section | Pitfalls prevent 80% of mistakes |
| Assume contracts are optional | Contracts are hard requirements |
| Start coding without reading Entry Points | Entry Points show the correct starting place |

---

## Success Metrics

After onboarding, the newcomer should be able to:

1. **Explain** - Describe project purpose in one sentence
2. **Navigate** - Find the right AGENTS.md for any task
3. **Comply** - Know constraints that apply to their area
4. **Avoid** - Know common pitfalls in their area
5. **Start** - Know exactly which file to open first

If any of these fail, the Intent Layer may need improvement via maintenance skill.
