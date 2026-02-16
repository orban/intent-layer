# skills/

> 5 top-level skills + 3 sub-skills. Each is a SKILL.md with YAML frontmatter that becomes a `/slash-command`.

## Purpose

Slash-command workflows that drive the Intent Layer lifecycle. Each skill is a directory containing a `SKILL.md` file with YAML frontmatter (`name`, `description`, `argument-hint`). Claude Code loads these as `/commands`.

### Skill map

| Skill | Command | What it does |
|-------|---------|-------------|
| `intent-layer` | `/intent-layer` | Smart router: detects state, presents relevant action. Setup (none/partial), review, maintain. |
| `intent-layer-maintain` | `/intent-layer:maintain` | Quarterly audits, post-incident updates (state = complete) |
| `intent-layer-query` | `/intent-layer:query` | Answer codebase questions using existing nodes |
| `intent-layer-health` | `/intent-layer:health` | Quick validation + staleness + coverage check |
| `intent-layer-review` | `/intent-layer:review` | Batch triage of pending learning reports (multiSelect) |

### Sub-skills (nested under `intent-layer/`)

| Sub-skill | Auto-invoked when | Script |
|-----------|-------------------|--------|
| `git-history` | Creating nodes for dirs with >50 commits | `mine_git_history.sh` |
| `pr-review-mining` | Creating nodes for dirs with merged PRs | `mine_pr_reviews.sh` |
| `pr-review` | Reviewing PRs touching Intent Layer nodes | `review_pr.sh` |

### Workflow references (under `intent-layer/workflows/`)

| File | Contents |
|------|----------|
| `setup.md` | Setup flow quick reference (extracted from main SKILL.md) |
| `maintain.md` | Maintenance flow quick reference (extracted from maintain skill) |
| `onboard.md` | Onboarding flow quick reference (extracted from former onboarding skill) |

## Entry Points

| Task | Start Here |
|------|------------|
| Create a new skill | Copy any existing skill dir, edit `SKILL.md` frontmatter |
| Understand a skill's behavior | Read its `SKILL.md` top to bottom (they're the full spec) |
| Add a sub-skill to `intent-layer` | Create dir under `intent-layer/`, add `SKILL.md` |
| Find which skill handles a state | Check the state routing: none/partial -> `intent-layer`, complete -> `intent-layer:maintain` |

## Contracts

- Every skill dir must contain exactly one `SKILL.md` with YAML frontmatter (`name`, `description`). Source: `.claude-plugin/plugin.json` auto-discovers skills.
- Skills reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/` -- never hardcode paths.
- Sub-skills live as subdirectories of a parent skill and get invoked by the parent's SKILL.md logic, not directly by users.
- Skill names use colon-namespaced format: `intent-layer:maintain`, `intent-layer:review`, etc. The root `intent-layer` skill has no suffix.

## Patterns

### State routing

```
detect_state.sh output -> skill selection
  none/partial -> /intent-layer (setup)
  complete     -> /intent-layer:maintain (audit)
```

All skills check state first and redirect if wrong.

### Learning review pipeline

```
Stop hook (auto-capture) → .intent-layer/mistakes/pending/ → /intent-layer:review (batch triage)
```

High-confidence learnings auto-integrate via `learn.sh`. Everything else queues for `/intent-layer:review`.

## Pitfalls

### Sub-skills aren't independently invocable

Users can't run `/git-history` or `/pr-review` directly. They're only triggered by the parent `intent-layer` skill's logic. The YAML `name` field in sub-skills matches but Claude Code only registers top-level skills.

### SKILL.md is both docs and executable spec

The SKILL.md content is injected into Claude's context when a skill runs. Everything in it is instructions to Claude, not documentation for humans. Writing "this skill does X" in SKILL.md means Claude reads it as instructions to do X. Be precise.
