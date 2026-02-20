# Setup Workflow

Quick reference for `/intent-layer` setup flow. See main `SKILL.md` for full details.

## Flow

1. `detect_state.sh` → none/partial → proceed; complete → redirect to `/intent-layer:maintain`
2. `estimate_all_candidates.sh` → measure all directories
3. Mine history: `mine_git_history.sh` + `mine_pr_reviews.sh` per directory
4. Create root node (CLAUDE.md) using template from `references/templates.md`
5. Create child AGENTS.md nodes for directories >20k tokens or responsibility shifts
6. `validate_node.sh` on each created node
7. Optional: symlink CLAUDE.md ↔ AGENTS.md for cross-tool compatibility

## Key Scripts

| Script | Purpose |
|--------|---------|
| `detect_state.sh` | Check state (none/partial/complete) |
| `estimate_all_candidates.sh` | Measure all candidate directories |
| `mine_git_history.sh` | Extract pitfalls from commits |
| `mine_pr_reviews.sh` | Extract pitfalls from PRs |
| `validate_node.sh` | Validate node quality |

## Decision Points

- **Root format**: CLAUDE.md (Anthropic) or AGENTS.md (cross-tool)
- **Template size**: Small (<50k), Medium (50-150k), Large (>150k)
- **Child node threshold**: >20k tokens or responsibility shift
- **Capture order**: leaf-first, then parents, then root
