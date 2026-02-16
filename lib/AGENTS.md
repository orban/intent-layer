# lib/

> 5 internal library scripts shared by hooks and other scripts. Not invoked directly by users.

## Purpose

Internal library scripts shared by hooks and other scripts. Not invoked directly.

```
common.sh              ← Sourced by everything. Utility functions.
find_covering_node.sh   ← Finds nearest AGENTS.md for a file path.
integrate_pitfall.sh    ← Writes accepted learnings into AGENTS.md.
aggregate_learnings.sh  ← Collects recent learnings for session injection.
check_mistake_history.sh ← Identifies high-risk directories by mistake count.
```

### Dependency graph

```
common.sh (no dependencies)
  ↑ sourced by all other lib scripts
  ↑ sourced by hook scripts in scripts/

find_covering_node.sh (standalone, no sourcing)
  ↑ called as subprocess by learn.sh, integrate_pitfall.sh

integrate_pitfall.sh → sources common.sh, calls find_covering_node.sh
aggregate_learnings.sh → sources common.sh
check_mistake_history.sh → standalone (reads mistake files directly)
```

## Entry Points

| Task | Start Here |
|------|------------|
| Use shared functions | `source "$SCRIPT_DIR/../lib/common.sh"` |
| Find covering node | Call `lib/find_covering_node.sh <path>` as subprocess |
| Add a new lib script | Create in `lib/`, add `set -euo pipefail` and `--help` |

## Contracts

- `common.sh` does NOT set `set -euo pipefail`. This is by design — the sourcing script controls its own shell strictness.
- All other lib scripts DO set `set -euo pipefail` and support `--help`.
- Environment variables that matter:
  - `CLAUDE_PROJECT_DIR` — project root for relative path resolution (default: `.`)
  - `CLAUDE_PLUGIN_ROOT` — plugin root for finding sibling scripts (auto-detected via `.claude-plugin/`)

## Patterns

### Key functions in common.sh

| Function | Purpose |
|----------|---------|
| `json_get <json> <path> [default]` | Parse JSON via jq with silent fallback to default if jq missing |
| `output_context <hook> <text>` | Emit hook JSON response (requires jq) |
| `output_block <reason>` | Emit blocking hook response |
| `calculate_word_overlap <a> <b>` | 0-100 overlap score. Filters words <3 chars, lowercases, deduplicates. |
| `get_plugin_root` | Auto-detect plugin root by walking up to `.claude-plugin/` |
| `require_jq` | Assert jq is installed, exit 1 with message if not |
| `extract_section_entries <file> <section>` | Extract entries under a `## Section` heading |
| `date_days_ago <n>` | Cross-platform date math (macOS/Linux) |
| `file_newer_than <file> <date>` | Cross-platform mtime check |

### integrate_pitfall.sh handles all learning types

Despite the name, it routes by filename prefix:
- `PITFALL-*` / `MISTAKE-*` / `SKELETON-*` → `## Pitfalls`
- `CHECK-*` → `## Checks`
- `PATTERN-*` → `## Patterns`
- `INSIGHT-*` → `## Context`

Each type has different formatting (checks get checklist items, patterns get `**Preferred**:` prefix).

## Pitfalls

### json_get silently returns defaults when jq is missing

`json_get` doesn't fail if jq isn't installed — it returns the default value. This is intentional for graceful degradation in hooks, but means you won't get an error if jq is unexpectedly absent. If you need jq, call `require_jq` first.

### find_covering_node.sh stops at .git boundary

The directory walk stops when it hits a `.git/` directory. It won't cross repo boundaries. This matters for monorepos with nested git repos.

### integrate_pitfall.sh is interactive by default

It prompts on duplicate detection. Use `--check-only` for non-interactive dedup checking or `--force` to skip dedup entirely. `learn.sh` (the newer script) handles dedup non-interactively.

### Entry body is truncated to 200 chars in integrate_pitfall.sh

`integrate_pitfall.sh` truncates body content to 200 characters and strips newlines. `learn.sh` does not truncate. If full body content matters, use `learn.sh`.
