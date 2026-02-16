# CLAUDE.md

> **TL;DR**: Intent Layer plugin for Claude Code - skills, agents, and hooks for managing AGENTS.md infrastructure.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Claude Code plugin providing tools for creating and maintaining Intent Layer infrastructure (hierarchical AGENTS.md/CLAUDE.md files that help AI agents navigate codebases).

## Installation

```bash
# Add the marketplace and install from GitHub
/plugin marketplace add orban/intent-layer
/plugin install intent-layer@orban

# Or from local directory
claude plugin install ./path/to/intent-layer-plugin
```

## Development

No build process. Skills are markdown files, agents are markdown files, scripts are bash.

```bash
# Validate a skill's SKILL.md
./scripts/validate_node.sh skills/intent-layer/SKILL.md

# Get help for any script
./scripts/detect_state.sh --help
```

## Architecture

### Plugin Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest (name, version, author)
├── skills/                   # Slash-command skills (/intent-layer, etc.)
│   ├── intent-layer/         # Main setup skill + sub-skills (git-history, pr-review, pr-review-mining)
│   ├── intent-layer-maintenance/
│   ├── intent-layer-onboarding/
│   ├── intent-layer-query/
│   ├── intent-layer-compound/ # End-of-session learning capture
│   ├── intent-layer-health/   # Quick health check
│   └── review-mistakes/       # Interactive mistake triage
├── agents/                   # Specialized subagents
│   ├── explorer.md           # Analyzes directories, proposes nodes
│   ├── validator.md          # Deep validation against codebase
│   ├── auditor.md            # Drift detection, staleness check
│   └── change-tracker.md     # Maps code changes to covering nodes
├── hooks/
│   └── hooks.json            # 5 hook slots (SessionStart, PreToolUse, PostToolUse, PostToolUseFailure, Stop)
├── mcp/                      # MCP context server (Python)
│   ├── server.py             # FastMCP server wrapping bash scripts
│   └── requirements.txt      # Python dependencies (mcp SDK)
├── scripts/                  # 32 standalone bash scripts
├── lib/                      # 5 internal library scripts
├── tests/                    # Bash test scripts
└── references/               # Templates, protocols, examples
```

### Components

| Component | Purpose | Invocation |
|-----------|---------|------------|
| **Skills** | Interactive workflows for setup/maintenance | `/intent-layer`, `/intent-layer-maintenance` |
| **Agents** | Specialized analysis tasks | Auto-invoked by Claude when relevant |
| **Hooks** | Learning loop: auto-capture, pitfall injection, staleness check | 5 hooks: SessionStart, PreToolUse, PostToolUse, PostToolUseFailure, Stop |

- **Injection log**: `.intent-layer/hooks/injections.log` — tracks which AGENTS.md entries were injected before edits
- **Outcome log**: `.intent-layer/hooks/outcomes.log` — tracks edit success/failure (telemetry). Opt out with `.intent-layer/disable-telemetry`

### Scripts

32 standalone bash tools in `scripts/`. CLI scripts support `-h`/`--help`; hook scripts don't.

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
| `show_status.sh` | Health dashboard with metrics |
| `show_hierarchy.sh` | Visual tree display of all nodes |
| `review_pr.sh` | Review PR against Intent Layer contracts |
| `capture_mistake.sh` | Record mistakes for learning loop (manual) |
| `review_mistakes.sh` | Interactive triage of pending mistake reports |
| `post-edit-check.sh` | Hook script for edit tracking |
| `stop-learning-check.sh` | Stop hook: two-tier learning classifier (heuristic + Haiku) |
| `inject-learnings.sh` | SessionStart hook: inject recent learnings |
| `pre-edit-check.sh` | PreToolUse hook: inject covering AGENTS.md sections |
| `capture-tool-failure.sh` | PostToolUseFailure hook: create skeleton reports |
| `audit_intent_layer.sh` | Comprehensive audit (validation + staleness + coverage) |
| `generate_orientation.sh` | Generate onboarding documents |
| `query_intent.sh` | Query Intent Layer for answers |
| `walk_ancestors.sh` | Navigate node hierarchy |
| `resolve_context.sh` | Single-call context resolver for agent swarms |
| `report_learning.sh` | Swarm-friendly non-interactive write-back |
| `learn.sh` | Direct-write learning to AGENTS.md (dedup-gated, single-agent only) |
| `generate_adapter.sh` | Export Intent Layer to other AI tools (cursor `.mdc`, raw markdown) |
| `show_telemetry.sh` | Dashboard: per-node success/failure rates, coverage gaps |
| `suggest_updates.sh` | AI-powered AGENTS.md update suggestions from git diffs (requires `curl`, `jq`, `ANTHROPIC_API_KEY`) |
| `apply_template.sh` | Apply starter templates to new projects |

### Library Scripts (lib/)

Internal scripts used by hooks and other scripts:

| Script | Purpose |
|--------|---------|
| `common.sh` | Shared functions (json_get, output_context, etc.) |
| `find_covering_node.sh` | Find nearest AGENTS.md for a file path |
| `check_mistake_history.sh` | Check if directory has mistake history |
| `aggregate_learnings.sh` | Aggregate recent accepted mistakes |
| `integrate_pitfall.sh` | Auto-add pitfalls to covering AGENTS.md |

### Skill Relationships

- `intent-layer` → Initial setup (state = none/partial)
- `intent-layer-maintenance` → Ongoing updates (state = complete)
- `intent-layer-onboarding` → Orientation for new developers
- `intent-layer-query` → Answer questions using Intent Layer
- `intent-layer:clean` → Remove Intent Layer from a repo
- `intent-layer-compound` → End-of-session learning capture and triage
- `intent-layer-health` → Quick health check (validation + staleness + coverage)
- `review-mistakes` → Interactive triage of pending mistake reports

All skills share scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/`.

## Key Concepts

- **Intent Layer**: Hierarchical AGENTS.md/CLAUDE.md files that help AI agents navigate codebases
- **Token budgets**: Each node <4k tokens, target 100:1 compression ratio
- **Three-tier boundaries**: Always/Ask First/Never pattern for permissions
- **Child nodes**: Named `AGENTS.md` (not CLAUDE.md) for cross-tool compatibility

### Information Architecture

#### How Ancestor Discovery Works

The hierarchy uses file-path-based traversal:

1. **Walk up directory tree** from target file/directory looking for `AGENTS.md` or `CLAUDE.md`
2. **Root identification**: First node found at repo root (typically `CLAUDE.md`)
3. **Child identification**: All `AGENTS.md` files in subdirectories beneath root

See `scripts/walk_ancestors.sh` for the implementation.

#### Loading Order

When working on a target file, nodes load in parent-before-child order:

1. Root node (project-wide context)
2. Intermediate ancestors (in descending order)
3. Target node (most specific context)

This ensures broad context is established before specific details.

#### T-Shaped Context Model

```
CLAUDE.md (root)              ← LOADED
    ├── src/
    │   ├── AGENTS.md         ← LOADED (ancestor)
    │   ├── api/
    │   │   └── AGENTS.md     ← TARGET (loaded)
    │   └── auth/
    │       └── AGENTS.md     ← NOT loaded (sibling)
    └── tests/
        └── AGENTS.md         ← NOT loaded (uncle)
```

- **Vertical axis**: All ancestors from root to target → loaded
- **Horizontal axis**: Siblings, cousins, uncles → NOT loaded

Why: Provides complete lineage without horizontal noise. Working in `src/api/` needs `src/` context but not `auth/` implementation details.

#### LCA (Lowest Common Ancestor) Placement

Facts that apply to multiple areas belong at their lowest common ancestor:

| Fact | Relevant Paths | Place At (LCA) |
|------|---------------|----------------|
| "All endpoints require auth" | `api/v1/*`, `api/v2/*` | `api/AGENTS.md` |
| "Never commit .env" | All paths | Root `CLAUDE.md` |
| "Use idempotency keys" | `payments/`, `billing/` | Their common parent |

This prevents duplication and drift. See `references/compression-techniques.md` for details.

### Agent Protocol

Intent Layer serves as a context protocol for agent swarms:

- **Read**: `resolve_context.sh <project> <path>` returns merged context from all ancestors
- **Write**: `report_learning.sh --project <p> --path <f> --type <t> --title <x> --detail <d>` queues a learning report
- **Spec**: See `references/agent-protocol.md` for the full protocol specification

Any tool that can read the filesystem can consume AGENTS.md nodes. The protocol is orchestrator-agnostic.

### MCP Context Server

Python MCP server (`mcp/server.py`) wrapping existing bash scripts via `FastMCP`. Exposes:

- `read_intent(project_root, target_path, sections?)` — merged ancestor context
- `report_learning(project_root, path, type, title, detail, agent_id?)` — queue a learning report
- `intent://{project}/{path}` resource — individual AGENTS.md/CLAUDE.md files

Requires `INTENT_LAYER_ALLOWED_PROJECTS` env var (colon-separated paths). All paths canonicalized with `os.path.realpath()` and validated for containment before use.

### Tool Adapter

`generate_adapter.sh` exports Intent Layer context to other AI tools:

- `--format cursor` → `.cursor/rules/*.mdc` files with YAML frontmatter
- `--format raw` → flat merged markdown on stdout

### Templates

Starter templates in `references/templates/` applied via `apply_template.sh`. v1 ships a `generic` template (root + src/ nodes). No variable engine — templates are static content.

## Entry Points

| Task | Start Here |
|------|------------|
| Create new skill | Copy `skills/intent-layer/`, edit `SKILL.md` frontmatter |
| Add/modify scripts | `scripts/` - standalone bash, no dependencies |
| Update templates | `references/templates/` — static `.template` files |
| Apply a template | `scripts/apply_template.sh <project> generic` |
| Export to Cursor | `scripts/generate_adapter.sh <project> --format cursor` |
| View telemetry | `scripts/show_telemetry.sh <project>` |
| Add new agent | Create `agents/<name>.md` with frontmatter |
| Modify hook behavior | Edit `hooks/hooks.json` or `scripts/post-edit-check.sh` |
| Test a script | Run directly: `./scripts/detect_state.sh --help` |

## Contracts

- Scripts must work standalone (no external dependencies beyond coreutils + bc)
- SKILL.md requires YAML frontmatter with `name` and `description`
- Agent markdown requires frontmatter with `description` and `capabilities`
- Scripts use `set -euo pipefail` for robust error handling
- All paths in scripts use `$TARGET_PATH` or `${CLAUDE_PLUGIN_ROOT}` variables
- All scripts support `-h`/`--help` for usage information
- Error messages go to stderr with actionable remediation hints
- Hook scripts must complete in <500ms

## Pitfalls

### Directory marketplace requires explicit plugin registration

Symlinking a plugin into a directory-based marketplace's plugins/ folder isn't enough. The plugin must also be listed in the marketplace's .claude-plugin/marketplace.json plugins array with name, version, and source path. Without the index entry, /plugin install returns 'not found'.

_Source: learn.sh | added: 2026-02-15_

- Token estimation uses bytes/4 approximation - not precise for non-ASCII text
- Scripts handle both macOS and Linux `stat` commands automatically
- `detect_state.sh` distinguishes symlinked AGENTS.md (expected) from duplicate files (warning)
- `mine_pr_reviews.sh` requires `gh` CLI and `jq` - other scripts only need coreutils + bc
- `suggest_updates.sh` requires `curl`, `jq`, and `ANTHROPIC_API_KEY` — falls back to dry-run without API key
- MCP server (`mcp/server.py`) requires `INTENT_LAYER_ALLOWED_PROJECTS` env var — refuses all requests without it
- Hook script receives tool input as JSON - parse carefully to avoid breaking on special characters

## Intent Layer

This project uses its own Intent Layer for documentation.

### Downlinks

| Area | Node | Description |
|------|------|-------------|
| Scripts | `scripts/AGENTS.md` | Script categories, arg parsing patterns, cross-platform gotchas |
| Library | `lib/AGENTS.md` | Shared functions, dependency graph, common.sh API |
| Hooks | `hooks/AGENTS.md` | Hook slots, data flow, stdin/stdout contracts, injection log |
| Skills | `skills/AGENTS.md` | Skill map, sub-skill invocation, state routing |
| Agents | `agents/AGENTS.md` | Subagent definitions, pipeline, frontmatter contracts |
| Eval Harness | `eval-harness/AGENTS.md` | A/B testing framework for Claude skills |
| MCP Server | `mcp/` | Python MCP server, path security, FastMCP patterns |
| Templates | `references/templates/` | Starter templates for new projects |

## Learning Loop

When you discover a non-obvious gotcha while working in this codebase:

1. **Identify the right AGENTS.md**: Find the nearest AGENTS.md to where the issue occurred
2. **Append to Pitfalls section**: Add a brief entry with:
   - **Problem**: What assumption failed or what was non-obvious
   - **Symptom**: Error message or unexpected behavior
   - **Solution**: How to handle it correctly
3. **Keep it concise**: 2-4 lines per pitfall, code references welcome

Example format:
```markdown
### API response format varies

**Problem**: `parse_response()` assumes dict, but API can return list
**Symptom**: `'list' object has no attribute 'get'`
**Solution**: Check `isinstance(data, list)` before calling `.get()`
```

This keeps the Intent Layer alive and useful for future sessions.
