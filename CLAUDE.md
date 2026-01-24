# CLAUDE.md

> **TL;DR**: Custom skills for Claude Code CLI - markdown files + bash scripts, symlinked to `~/.claude/skills/`.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Custom skills for Claude Code CLI. Skills are symlinked to `~/.claude/skills/` for use across projects.

## Development

No build process. Skills are markdown files with bash scripts.

```bash
# Install skills (symlink to Claude Code skills directory)
ln -s ~/dev/claude-skills/intent-layer ~/.claude/skills/intent-layer
ln -s ~/dev/claude-skills/intent-layer-maintenance ~/.claude/skills/intent-layer-maintenance

# Validate a skill's SKILL.md
./intent-layer/scripts/validate_node.sh intent-layer/SKILL.md

# Get help for any script
./intent-layer/scripts/detect_state.sh --help
```

## Architecture

### Skill Structure

Each skill follows this pattern:
```
skill-name/
├── SKILL.md              # Main skill documentation (frontmatter + content)
├── scripts/              # Bash automation scripts
└── references/           # Templates, examples, protocols
```

The `SKILL.md` file has YAML frontmatter with `name`, `description`, and optional `argument-hint` fields.

### Scripts

Scripts are standalone bash tools in `intent-layer/scripts/`. All support `-h`/`--help`.

| Script | Purpose |
|--------|---------|
| `detect_state.sh` | Check Intent Layer state (none/partial/complete) |
| `analyze_structure.sh` | Find semantic boundaries |
| `estimate_tokens.sh` | Measure single directory |
| `estimate_all_candidates.sh` | Measure all candidate directories |
| `validate_node.sh` | Validate CLAUDE.md/AGENTS.md quality |
| `capture_pain_points.sh` | Generate maintenance capture template |
| `capture_state.sh` | Track open questions during capture |
| `detect_changes.sh` | Find affected nodes on merge/PR |
| `detect_staleness.sh` | Find nodes that may need updates |
| `mine_git_history.sh` | Extract insights from git commits |
| `mine_pr_reviews.sh` | Extract insights from GitHub PRs |
| `show_status.sh` | Health dashboard with metrics and recommendations |
| `show_hierarchy.sh` | Visual tree display of all nodes |
| `review_pr.sh` | Review PR against Intent Layer contracts |
| `capture_mistake.sh` | Record mistakes for learning loop |

### Skill Relationship

`intent-layer` handles initial setup (state = none/partial).
`intent-layer-maintenance` handles ongoing maintenance (state = complete).
`intent-layer:clean` removes Intent Layer from a repo (deletes child AGENTS.md, strips section from root).

The maintenance skill references scripts from intent-layer via `~/.claude/skills/intent-layer/scripts/`.

## Key Concepts

- **Intent Layer**: Hierarchical AGENTS.md/CLAUDE.md files that help AI agents navigate codebases
- **Token budgets**: Each node <4k tokens, target 100:1 compression ratio
- **Three-tier boundaries**: Always/Ask First/Never pattern for permissions
- **Child nodes**: Named `AGENTS.md` (not CLAUDE.md) for cross-tool compatibility

## Intent Layer

> TL;DR: Claude Code skills for setting up AGENTS.md infrastructure in codebases. See Entry Points below.

### Entry Points

| Task | Start Here |
|------|------------|
| Create new skill | Copy existing skill directory, edit `SKILL.md` frontmatter |
| Add/modify scripts | `intent-layer/scripts/` - standalone bash, no dependencies |
| Update templates | `intent-layer/references/templates.md` |
| Test a script | Run directly: `./intent-layer/scripts/detect_state.sh --help` |

### Contracts

- Scripts must work standalone (no external dependencies beyond coreutils + bc)
- SKILL.md requires YAML frontmatter with `name` and `description`
- Scripts use `set -euo pipefail` for robust error handling
- All paths in scripts use `$TARGET_PATH` variable, not hardcoded paths
- All scripts support `-h`/`--help` for usage information
- Error messages go to stderr with actionable remediation hints

### Pitfalls

- `intent-layer-maintenance` skill references scripts via `~/.claude/skills/intent-layer/scripts/` - if intent-layer isn't symlinked, maintenance skill breaks
- Token estimation uses bytes/4 approximation - not precise for non-ASCII text
- Scripts handle both macOS and Linux `stat` commands automatically
- `detect_state.sh` distinguishes symlinked AGENTS.md (expected) from duplicate files (warning)
- `mine_pr_reviews.sh` requires `gh` CLI and `jq` - other scripts only need coreutils + bc
