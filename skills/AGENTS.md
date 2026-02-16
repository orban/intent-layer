# skills/

> 7 top-level skills + 3 sub-skills. Each is a SKILL.md with YAML frontmatter that becomes a `/slash-command`.

## Purpose

Slash-command workflows that drive the Intent Layer lifecycle. Each skill is a directory containing a `SKILL.md` file with YAML frontmatter (`name`, `description`, `argument-hint`). Claude Code loads these as `/commands`.

### Skill map

| Skill | Trigger | What it does |
|-------|---------|-------------|
| `intent-layer` | `/intent-layer` | Initial setup (state = none/partial). Runs detect, measure, mine, create, validate. |
| `intent-layer-maintenance` | `/intent-layer-maintenance` | Quarterly audits, post-incident updates (state = complete) |
| `intent-layer-query` | `/intent-layer-query` | Answer codebase questions using existing nodes |
| `intent-layer-onboarding` | `/intent-layer-onboarding` | Orient new developers via hierarchy walkthrough |
| `intent-layer-compound` | `/intent-layer-compound` | End-of-session learning capture: conversation scan, structured prompts, direct integration |
| `intent-layer-health` | `/intent-layer-health` | Quick validation + staleness + coverage check |
| `review-mistakes` | `/review-mistakes` | Interactive triage of pending mistake reports |

### Sub-skills (nested under `intent-layer/`)

| Sub-skill | Auto-invoked when | Script |
|-----------|-------------------|--------|
| `git-history` | Creating nodes for dirs with >50 commits | `mine_git_history.sh` |
| `pr-review-mining` | Creating nodes for dirs with merged PRs | `mine_pr_reviews.sh` |
| `pr-review` | Reviewing PRs touching Intent Layer nodes | `review_pr.sh` |

## Entry Points

| Task | Start Here |
|------|------------|
| Create a new skill | Copy any existing skill dir, edit `SKILL.md` frontmatter |
| Understand a skill's behavior | Read its `SKILL.md` top to bottom (they're the full spec) |
| Add a sub-skill to `intent-layer` | Create dir under `intent-layer/`, add `SKILL.md` |
| Find which skill handles a state | Check the state routing: none/partial -> `intent-layer`, complete -> `intent-layer-maintenance` |

## Contracts

- Every skill dir must contain exactly one `SKILL.md` with YAML frontmatter (`name`, `description`). Source: `.claude-plugin/plugin.json` auto-discovers skills.
- Skills reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/` -- never hardcode paths.
- Sub-skills live as subdirectories of a parent skill and get invoked by the parent's SKILL.md logic, not directly by users.
- `intent-layer-compound` writes via `learn.sh` (direct, dedup-gated). Never via `report_learning.sh` (that's for multi-agent swarms).

## Patterns

### State routing

```
detect_state.sh output -> skill selection
  none/partial -> /intent-layer (setup)
  complete     -> /intent-layer-maintenance (audit)
```

All skills check state first and redirect if wrong.

### Prompts directory

`intent-layer-compound/prompts/scan.md` is a reusable prompt template. Other skills inline their prompts directly in SKILL.md. No standard yet for when to extract prompts.

## Pitfalls

### Sub-skills aren't independently invocable

Users can't run `/git-history` or `/pr-review` directly. They're only triggered by the parent `intent-layer` skill's logic. The YAML `name` field in sub-skills matches but Claude Code only registers top-level skills.

### SKILL.md is both docs and executable spec

The SKILL.md content is injected into Claude's context when a skill runs. Everything in it is instructions to Claude, not documentation for humans. Writing "this skill does X" in SKILL.md means Claude reads it as instructions to do X. Be precise.

### intent-layer-compound uses conversation analysis

Layer 1 (AI scan) searches the current conversation for correction signals ("actually...", "no, you should..."). This only works when run in the same session. Running it in a fresh session finds nothing.
