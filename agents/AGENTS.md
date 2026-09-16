# agents/

> 4 specialized subagents. Markdown files with YAML frontmatter (`description`, `capabilities`) that Claude auto-invokes for analysis tasks.

## Contracts

- YAML frontmatter must include `description` (string) and `capabilities` (list).
- Agents reference scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/` and `${CLAUDE_PLUGIN_ROOT}/lib/`.
- Agents produce markdown output, not JSON. Reports use the table/heading format shown in each agent file.
- `change-tracker.md` also has a `triggers` frontmatter field listing when it fires.

### Agent pipeline

```
Explorer -> Validator -> (user approves) -> write AGENTS.md
Auditor -> ChangeTracker -> Validator (targeted)
```

## Rules

### Agents aren't guaranteed to run

Claude decides whether to use an agent based on context. The `description` field is what Claude matches against — vague descriptions mean the agent gets skipped.

### Validator does structural AND semantic checks

`validate_node.sh` (the script) does structural validation only (token count, required sections, paths). The Validator agent does deeper semantic checks (are contracts enforced in code? do ownership mappings exist?). Don't confuse the two.

### ChangeTracker severity depends on node content

Severity classification (HIGH/MEDIUM/LOW) reads the node's Ownership section to determine if a changed file is "important". Stale Ownership means wrong severity.

## Ownership

| Agent | When invoked | Does what |
|-------|-------------|-----------|
| `explorer.md` | Setting up new nodes or adding coverage | Analyzes directory structure, mines history, drafts AGENTS.md |
| `validator.md` | After creating/updating nodes, or PR review | Deep semantic validation (contracts enforced? rules current?) |
| `auditor.md` | Quarterly maintenance, post-merge | Discovers all nodes, checks staleness, spawns validator per node |
| `change-tracker.md` | Before PR merge, after git pull | Maps changed files to covering nodes, classifies severity |
