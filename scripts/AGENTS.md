# scripts/

> 27 standalone bash scripts. CLI tools and hook handlers for the Intent Layer lifecycle.

## Purpose

27 standalone bash scripts covering the Intent Layer lifecycle. Scripts fall into five categories:

- **Detection** (7): `detect_state.sh`, `detect_changes.sh`, `detect_staleness.sh`, `audit_intent_layer.sh`, `analyze_structure.sh`, `estimate_tokens.sh`, `estimate_all_candidates.sh`
- **Capture & Learning** (5): `learn.sh`, `report_learning.sh`, `capture_mistake.sh`, `capture_pain_points.sh`, `capture_state.sh`
- **Display & Retrieval** (6): `show_status.sh`, `show_hierarchy.sh`, `walk_ancestors.sh`, `query_intent.sh`, `resolve_context.sh`, `generate_orientation.sh`
- **Hook handlers** (4): `inject-learnings.sh`, `pre-edit-check.sh`, `post-edit-check.sh`, `capture-tool-failure.sh`
- **Mining & Review** (5): `mine_git_history.sh`, `mine_pr_reviews.sh`, `review_pr.sh`, `review_mistakes.sh`, `validate_node.sh`

## Entry Points

| Task | Start Here |
|------|------------|
| Add a new CLI script | Copy an existing script, follow the arg parsing pattern below |
| Add a new hook script | See `hooks/AGENTS.md` for stdin/stdout contracts |
| Debug a script | Run with `--help`, then test directly: `./scripts/detect_state.sh` |
| Add a learning mode | Decide: `learn.sh` (direct) vs `report_learning.sh` (queued) |

## Patterns

### Arg parsing

All CLI scripts use the same loop pattern. Follow it for new scripts:

```bash
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --flag) VAR="$2"; shift 2 ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done
```

### Two learning modes

Pick the right one:

| Mode | Script | When to use |
|------|--------|-------------|
| Direct write | `learn.sh` | Single-agent sessions. Writes to AGENTS.md with dedup gate. |
| Pending queue | `report_learning.sh` | Multi-agent swarms. Creates pending report for human review. |

Calling `learn.sh --agent-id` errors on purpose, directing to `report_learning.sh`.

### Library sourcing

Scripts that need shared functions source `lib/common.sh` via:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
```

Hook scripts use `CLAUDE_PLUGIN_ROOT` instead of `SCRIPT_DIR`. Exception: `post-edit-check.sh` doesn't source `common.sh` at all — it's a standalone script that outputs plain text.

## Contracts

- CLI scripts support `--help`. Hook scripts don't (they read JSON on stdin, not CLI args).
- `set -euo pipefail` on all scripts. Two legacy exceptions: `capture_pain_points.sh` and `capture_state.sh` use `set -e` only.
- Exit code 2 means "duplicate detected" in learning scripts (not an error, an intentional skip).

## Pitfalls

### Hook scripts vs CLI scripts have different I/O contracts

Hook scripts (`inject-learnings.sh`, `pre-edit-check.sh`, `capture-tool-failure.sh`) read JSON on stdin and output JSON via `output_context()`. They don't parse CLI args or support `--help`. Don't add `--help` to them.

### Cross-platform stat and date commands

macOS and Linux have different `stat` and `date` flags. Always try macOS first, fall back to Linux:
- `stat -f %m` (macOS) vs `stat -c %Y` (Linux)
- `date -v-7d` (macOS) vs `date -d "7 days ago"` (Linux)

See `lib/common.sh` for the canonical pattern. Don't invent a new one.

### capture_mistake.sh uses eval in prompt()

The `prompt()` function at line 117 uses `eval` to set variables dynamically. This is intentional but fragile for shell parsing. Don't refactor it without understanding why it's there.

### find exclusions must use arrays, not string concatenation

`detect_state.sh` builds `find` exclusions as a bash array. Never build find args via string concatenation or `eval` — injection risk. Follow the array pattern.
