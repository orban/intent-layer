# agents/

> 4 specialized subagents. Markdown files with YAML frontmatter (`description`, `capabilities`) that Claude auto-invokes for analysis tasks.

## Purpose

Subagent definitions for Intent Layer analysis. Each is a markdown file that Claude reads when it needs specialized analysis capabilities. They aren't slash commands -- Claude picks them up contextually based on task type.

### Agent map

| Agent | When invoked | Does what |
|-------|-------------|-----------|
| `explorer.md` | Setting up new nodes or adding coverage | Analyzes directory structure, mines history, drafts AGENTS.md |
| `validator.md` | After creating/updating nodes, or PR review | Deep semantic validation (contracts enforced? entry points exist?) |
| `auditor.md` | Quarterly maintenance, post-merge | Discovers all nodes, checks staleness, spawns validator per node |
| `change-tracker.md` | Before PR merge, after git pull | Maps changed files to covering nodes, classifies severity |

### Agent pipeline

```
Explorer -> Validator -> (user approves) -> write AGENTS.md
Auditor -> ChangeTracker -> Validator (targeted)
```

Explorer creates drafts. Validator checks accuracy. Auditor orchestrates full audits. ChangeTracker narrows scope so Validator doesn't re-check everything.

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new agent | Create `agents/<name>.md` with `description` and `capabilities` in YAML frontmatter |
| Understand agent invocation | Agents are contextual -- Claude reads them when tasks match their `description` field |
| Modify audit behavior | Edit `auditor.md` (orchestration) or `validator.md` (per-node checks) |

## Contracts

- YAML frontmatter must include `description` (string) and `capabilities` (list). Source: `CLAUDE.md` root contracts.
- Agents reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/` and `${CLAUDE_PLUGIN_ROOT}/lib/`.
- Agents produce markdown output, not JSON. Reports use the table/heading format shown in each agent file.
- `change-tracker.md` also has a `triggers` frontmatter field listing when it fires.

## Pitfalls

### Agents aren't guaranteed to run

Claude decides whether to use an agent based on context. There's no hook or trigger that forces invocation. The `description` field is what Claude matches against, so vague descriptions mean the agent gets skipped.

### Validator does structural AND semantic checks

`validate_node.sh` (the script) does structural validation only (token count, required sections, paths). The Validator agent does deeper semantic checks (are contracts actually enforced in code? do entry points exist?). Don't confuse the two.

### ChangeTracker severity depends on node content

Severity classification (HIGH/MEDIUM/LOW) reads the node's Entry Points section to determine if a changed file is "important". If Entry Points are stale, severity assessment is wrong too.
