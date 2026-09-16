# lib/

> 5 internal library scripts shared by hooks and other scripts. Not invoked directly by users.

## Contracts

- `common.sh` does NOT set `set -euo pipefail`. The sourcing script controls its own shell strictness.
- All other lib scripts DO set `set -euo pipefail` and support `--help`.
- Environment variables that matter:
  - `CLAUDE_PROJECT_DIR` — project root for relative path resolution (default: `.`)
  - `CLAUDE_PLUGIN_ROOT` — plugin root for finding sibling scripts (auto-detected via `.claude-plugin/`)

### Key functions in common.sh

| Function | Purpose |
|----------|---------|
| `json_get <json> <path> [default]` | Parse JSON via jq with silent fallback to default if jq missing |
| `output_context <hook> <text>` | Emit hook JSON response (requires jq) |
| `output_block <reason>` | Emit blocking hook response |
| `calculate_word_overlap <a> <b>` | 0-100 overlap score. Filters words <3 chars. |
| `get_plugin_root` | Auto-detect plugin root by walking up to `.claude-plugin/` |
| `require_jq` | Assert jq is installed, exit 1 if not |
| `extract_section_entries <file> <section>` | Extract entries under a `## Section` heading |
| `date_days_ago <n>` | Cross-platform date math (macOS/Linux) |

## Boundaries

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

## Rules

### json_get silently returns defaults when jq is missing

`json_get` doesn't fail if jq isn't installed — returns default value. Intentional for graceful degradation in hooks. If you need jq, call `require_jq` first.

### find_covering_node.sh stops at .git boundary

The directory walk stops at `.git/`. Won't cross repo boundaries. Matters for monorepos with nested git repos.

### integrate_pitfall.sh routes all learning types to Rules

Despite the name, it routes all types (`PITFALL-*`, `MISTAKE-*`, `SKELETON-*`, `CHECK-*`, `PATTERN-*`, `INSIGHT-*`) to the `## Rules` section. Each type has different formatting.

### integrate_pitfall.sh is interactive by default

Prompts on duplicate detection. Use `--check-only` for non-interactive dedup or `--force` to skip. `learn.sh` handles dedup non-interactively.

### Entry body is truncated to 200 chars in integrate_pitfall.sh

`integrate_pitfall.sh` truncates body content to 200 characters. `learn.sh` does not. Use `learn.sh` when full body matters.
