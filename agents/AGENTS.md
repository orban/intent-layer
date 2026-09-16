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

## Agent pipeline

```
Explorer -> Validator -> (user approves) -> write AGENTS.md
Auditor -> ChangeTracker -> Validator (targeted)
```

## Code Map

| Path | Covered by | Context Type |
|------|------------|--------------|
| `agents/` | `agents/AGENTS.md` | Agent definitions & registry |
| `scripts/` | `scripts/AGENTS.md` | CLI tools & hook logic |
| `lib/` | `lib/AGENTS.md` | Shared library functions |
| `hooks/` | `hooks/AGENTS.md` | Lifecycle hooks & data flow |

## Entry Points

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new agent | Create `agents/<name>.md` with `description` and `capabilities` in YAML frontmatter |
| Understand agent invocation | Agents are contextual -- Claude reads them when tasks match their `description` field |
| Modify audit behavior | Edit `auditor.md` (orchestration) or `validator.md` (per-node checks) |

## Patterns

| Pattern | Usage | Note |
|---------|-------|------|
| Contextual Invocation | Claude's internal router | Driven by agent description matches |
| Sequential Pipeline | Agent orchestration | Explorer -> Validator -> Human Review -> Commit |

## Boundaries

| Permission | Scope | Action |
|------------|-------|--------|
| **Always** | Read-only | Inspecting `AGENTS.md` and `CLAUDE.md` for context |
| **Ask First** | Writing/Editing | Modifying any `.md` files in the repository |
| **Never** | Destructive Actions | Deleting directories or uncommitted file changes |

## Contracts

- YAML frontmatter must include `description` (string) and `capabilities` (list). Source: `CLAUDE.md` root contracts.
