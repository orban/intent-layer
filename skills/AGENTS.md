# skills/

> 7 top-level skills + 3 sub-skills. Each is a SKILL.md with YAML frontmatter that becomes a `/slash-command`.

## Contracts

- Every skill dir must contain exactly one `SKILL.md` with YAML frontmatter (`name`, `description`). Auto-discovered by `.claude-plugin/plugin.json`.
- Skills reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/` — never hardcode paths.
- Sub-skills live as subdirectories of a parent skill, invoked by the parent's SKILL.md logic, not directly by users.
- `intent-layer-compound` writes via `learn.sh` (direct, dedup-gated). Never via `report_learning.sh` (that's for multi-agent swarms).
- State routing:

```
detect_state.sh output -> skill selection
  none/partial -> /intent-layer (setup)
  complete     -> /intent-layer-maintenance (audit)
```

## Rules

### Sub-skills aren't independently invocable

Users can't run `/git-history` or `/pr-review` directly. They're only triggered by the parent `intent-layer` skill's logic.

### SKILL.md is both docs and executable spec

The SKILL.md content is injected into Claude's context when a skill runs. Everything in it is instructions to Claude, not documentation for humans. Be precise.

### intent-layer-compound uses conversation analysis

Layer 1 (AI scan) searches the current conversation for correction signals ("actually...", "no, you should..."). Only works in the same session.

## Ownership

| Skill | Trigger | What it does |
|-------|---------|-------------|
| `intent-layer` | `/intent-layer` | Initial setup (state = none/partial) |
| `intent-layer-maintenance` | `/intent-layer-maintenance` | Quarterly audits, post-incident updates (state = complete) |
| `intent-layer-query` | `/intent-layer-query` | Answer codebase questions using existing nodes |
| `intent-layer-onboarding` | `/intent-layer-onboarding` | Orient new developers via hierarchy walkthrough |
| `intent-layer-compound` | `/intent-layer-compound` | End-of-session learning capture |
| `intent-layer-health` | `/intent-layer-health` | Quick validation + staleness + coverage check |
| `review-mistakes` | `/review-mistakes` | Interactive triage of pending mistake reports |

### Sub-skills (nested under `intent-layer/`)

| Sub-skill | Auto-invoked when | Script |
|-----------|-------------------|--------|
| `git-history` | Creating nodes for dirs with >50 commits | `mine_git_history.sh` |
| `pr-review-mining` | Creating nodes for dirs with merged PRs | `mine_pr_reviews.sh` |
| `pr-review` | Reviewing PRs touching Intent Layer nodes | `review_pr.sh` |
