# scripts/

> 28 standalone bash scripts. CLI tools and hook handlers for the Intent Layer lifecycle.

## Contracts

- CLI scripts support `--help`. Hook scripts don't (they read JSON on stdin, not CLI args).
- `set -euo pipefail` on all scripts. Two legacy exceptions: `capture_pain_points.sh` and `capture_state.sh` use `set -e` only.
- Exit code 2 means "duplicate detected" in learning scripts (not an error, an intentional skip).
- All CLI scripts use the same arg parsing loop:

```bash
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        --flag) VAR="$2"; shift 2 ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done
```

- Scripts source `lib/common.sh` via:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
```

Hook scripts use `CLAUDE_PLUGIN_ROOT` instead. Exception: `post-edit-check.sh` doesn't source `common.sh`.

## Rules

### Hook scripts vs CLI scripts have different I/O contracts

Hook scripts (`inject-learnings.sh`, `pre-edit-check.sh`, `capture-tool-failure.sh`, `stop-learning-check.sh`) read JSON on stdin and output JSON via `output_context()` or `output_block()`. Don't add `--help` to them. Exception: `post-edit-check.sh` receives file path as `$1` and outputs plain text.

### Cross-platform stat and date commands

macOS and Linux have different `stat` and `date` flags. Always try macOS first, fall back to Linux. See `lib/common.sh` for the canonical pattern. Don't invent a new one.

### capture_mistake.sh uses eval in prompt()

The `prompt()` function at line 117 uses `eval` to set variables dynamically. Intentional but fragile. Don't refactor without understanding why.

### find exclusions must use arrays, not string concatenation

`detect_state.sh` builds `find` exclusions as a bash array. Never use string concatenation or `eval` — injection risk.

## Ownership

Five script categories:

- **Detection** (7): `detect_state.sh`, `detect_changes.sh`, `detect_staleness.sh`, `audit_intent_layer.sh`, `analyze_structure.sh`, `estimate_tokens.sh`, `estimate_all_candidates.sh`
- **Capture & Learning** (5): `learn.sh`, `report_learning.sh`, `capture_mistake.sh`, `capture_pain_points.sh`, `capture_state.sh`
- **Display & Retrieval** (6): `show_status.sh`, `show_hierarchy.sh`, `walk_ancestors.sh`, `query_intent.sh`, `resolve_context.sh`, `generate_orientation.sh`
- **Hook handlers** (5): `inject-learnings.sh`, `pre-edit-check.sh`, `post-edit-check.sh`, `capture-tool-failure.sh`, `stop-learning-check.sh`
- **Mining & Review** (5): `mine_git_history.sh`, `mine_pr_reviews.sh`, `review_pr.sh`, `review_mistakes.sh`, `validate_node.sh`

| Task | Start here |
|------|------------|
| Add a new CLI script | Copy an existing script, follow the arg parsing pattern in Contracts |
| Add a new hook script | See `hooks/AGENTS.md` for stdin/stdout contracts |
| Add a learning mode | Decide: `learn.sh` (direct, dedup-gated) vs `report_learning.sh` (queued, multi-agent) |

### stop-learning-check.sh three-tier architecture

1. **Tier 1** (bash heuristics): No signals → exit 0.
2. **Tier 2** (Haiku classifier): Binary `should_capture: true/false`.
3. **Tier 3** (Haiku extraction): High-confidence → `learn.sh` (auto-write). Low-confidence → `report_learning.sh` (pending queue). All tiers fail open.
