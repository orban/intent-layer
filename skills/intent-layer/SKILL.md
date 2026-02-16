---
name: intent-layer
description: >
  Smart router for Intent Layer commands. Detects project state and routes to the
  right action: setup, review pending learnings, maintenance, query, health check,
  onboarding, or export.
argument-hint: "[/path/to/project]"
---

# Intent Layer

> **TL;DR**: Detects your project's Intent Layer state and routes you to the right action.

## Step 1: Detect State

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/detect_state.sh "${1:-.}"
```

Capture the output. It returns one of: `none`, `partial`, `complete`.

If the command fails, tell the user:

> State detection failed. Run `detect_state.sh --help` for troubleshooting.

Then stop.

## Step 2: Count Pending Learnings

```bash
find "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/pending" -name "*.md" -type f 2>/dev/null | wc -l
```

Store the count as `PENDING_COUNT`.

## Step 3: Route

Use this matrix to decide what to do:

| State | Pending | Action |
|-------|---------|--------|
| `none` | any | → **Setup** |
| `partial` | any | → **Continue Setup** |
| `complete` | >0 | → **Review** |
| `complete` | 0 | → **Menu** |

### Route: Setup (state = none)

Tell the user:

> No Intent Layer found. Want to set one up?

Use `AskUserQuestion` with options:
- "Yes, set up now" — proceed with setup workflow below
- "Not now" — stop

If they choose setup, follow the **Setup Workflow** (see `workflows/setup.md` for quick reference).

The full setup flow is:
1. `estimate_all_candidates.sh` to measure directories
2. Mine history: `mine_git_history.sh` + `mine_pr_reviews.sh` per candidate
3. Create root node using template from `references/templates.md`
4. Create child AGENTS.md for directories >20k tokens or with responsibility shifts
5. `validate_node.sh` on each created node
6. Optional symlink for cross-tool compatibility

For large codebases (>200k tokens), use parallel subagents — one per subsystem for exploration + mining.

### Route: Continue Setup (state = partial)

Tell the user:

> Intent Layer partially set up. CLAUDE.md exists but needs an Intent Layer section or child nodes.

Use `AskUserQuestion` with options:
- "Continue setup" — run setup workflow from where it left off
- "Not now" — stop

### Route: Review (state = complete, pending > 0)

Tell the user:

> Intent Layer active. **{PENDING_COUNT} learning(s) pending review.**

Use `AskUserQuestion` with options:
- "Review now" — invoke `/intent-layer:review` skill
- "Skip, show menu" — fall through to Menu

### Route: Menu (state = complete, pending = 0)

Tell the user:

> Intent Layer healthy. What would you like to do?

Use `AskUserQuestion` with options:
- "Run maintenance check" — invoke `/intent-layer:maintain`
- "Query the Intent Layer" — invoke `/intent-layer:query`
- "Run health check" — invoke `/intent-layer:health`
- "Generate onboarding doc" — follow onboarding workflow (see `workflows/onboard.md`)

---

## Sub-Skills

These are **automatically invoked** during setup when appropriate:

| Sub-Skill | Location | Auto-Invoke When |
|-----------|----------|------------------|
| `git-history` | `git-history/SKILL.md` | Creating nodes for dirs with >50 commits |
| `pr-review-mining` | `pr-review-mining/SKILL.md` | Creating nodes for dirs with merged PRs |
| `pr-review` | `pr-review/SKILL.md` | Reviewing PRs touching Intent Layer nodes |

### learning-loop (Auto-Invoked on Error Discovery)

When you discover a non-obvious gotcha during any work:
1. Find the nearest AGENTS.md
2. Append to its Pitfalls section
3. Format: `### Short title` + Problem/Symptom/Solution

---

## Workflow References

Detailed procedures for each major workflow:

| Workflow | Reference File |
|----------|---------------|
| Setup (initial creation) | `workflows/setup.md` |
| Maintenance (audits, updates) | `workflows/maintain.md` |
| Onboarding (orient newcomers) | `workflows/onboard.md` |

---

## Related Commands

| Command | Purpose |
|---------|---------|
| `/intent-layer:maintain` | Quarterly audits, post-incident updates |
| `/intent-layer:query` | Answer questions using Intent Layer |
| `/intent-layer:health` | Quick validation + staleness check |
| `/intent-layer:review` | Batch triage pending learnings |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `detect_state.sh` | Check Intent Layer state (none/partial/complete) |
| `analyze_structure.sh` | Find semantic boundaries |
| `estimate_tokens.sh` | Measure single directory |
| `estimate_all_candidates.sh` | Measure all candidates at once |
| `validate_node.sh` | Check node quality before committing |
| `show_status.sh` | Health dashboard with metrics |
| `show_hierarchy.sh` | Visual tree display of all nodes |
| `mine_git_history.sh` | Extract insights from git commits |
| `mine_pr_reviews.sh` | Extract insights from GitHub PRs |
| `generate_adapter.sh` | Export to Cursor / raw markdown |

All paths: `${CLAUDE_PLUGIN_ROOT}/scripts/`

---

## Core Rules

- **One root only**: CLAUDE.md and AGENTS.md should not coexist at root. Pick one, symlink the other.
- **Child nodes named AGENTS.md**: For cross-tool compatibility.
- **Token budgets**: Each node <4k tokens (prefer <3k). Target 100:1 compression.
- **Capture order**: Leaf-first, then parents, then root. Clarity compounds upward.
- **When to create child nodes**: >20k tokens in directory OR responsibility shift. Don't create for every directory.
