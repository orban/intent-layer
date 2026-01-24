# Intent Layer Plugin

Claude Code plugin for creating and maintaining Intent Layer infrastructure.

## Philosophy

Intent Layers solve a fundamental problem: **AI agents reading raw code lack the tribal knowledge that experienced engineers have.**

Senior engineers know:
- Where to start for common tasks
- What patterns are expected
- What invariants must never be violated
- What pitfalls to avoid

Intent Layers compress this knowledge into high-signal AGENTS.md/CLAUDE.md files that give agents the same intuition—without reading thousands of lines of code.

### Core Principles

1. **Compression > Verbosity** - Target 100:1 compression. 200k tokens of code → 2k token node.
2. **Contracts > Comments** - Document invariants and constraints, not obvious code behavior.
3. **Pitfalls > Patterns** - What catches people matters more than standard patterns.
4. **Progressive Disclosure** - Start minimal, agents drill down when needed.

## Installation

```bash
# Install from local directory
claude plugin install ./path/to/intent-layer-plugin

# Or from a marketplace
claude plugin install intent-layer@marketplace-name
```

## Components

### Skills

Interactive workflows invoked via slash commands:

| Skill | Purpose | Command |
|-------|---------|---------|
| `intent-layer` | Set up new Intent Layer infrastructure | `/intent-layer` |
| `intent-layer-maintenance` | Maintain existing Intent Layers | `/intent-layer-maintenance` |
| `intent-layer-onboarding` | Orient new developers using Intent Layer | `/intent-layer-onboarding` |
| `intent-layer-query` | Query Intent Layer for answers | `/intent-layer-query` |

### Agents

Specialized subagents that Claude invokes automatically when appropriate:

| Agent | Purpose |
|-------|---------|
| `explorer` | Analyze directories and propose AGENTS.md content |
| `validator` | Deep validation that nodes accurately reflect codebase |
| `auditor` | Find drift between nodes and current code state |

### Hooks

Automatic event handlers:

| Hook | Event | Purpose |
|------|-------|---------|
| `post-edit-check` | PostToolUse (Edit/Write) | Remind about Intent Layer coverage |

## Usage

### Initial Setup

```bash
# Check if Intent Layer exists
./scripts/detect_state.sh /path/to/project

# Analyze token distribution
./scripts/estimate_all_candidates.sh /path/to/project

# Create nodes using the skill
# Then in Claude Code: /intent-layer /path/to/project
```

### Maintenance

```bash
# Detect which nodes need review after changes
./scripts/detect_changes.sh main HEAD

# Generate pain point capture template
./scripts/capture_pain_points.sh pain_points.md

# Run maintenance workflow
# In Claude Code: /intent-layer-maintenance /path/to/project
```

### Onboarding

```bash
# Generate orientation overview
./scripts/generate_orientation.sh /path/to/project

# Or use the skill interactively
# In Claude Code: /intent-layer-onboarding /path/to/project
```

## Plugin Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/                   # Slash-command skills
│   ├── intent-layer/
│   ├── intent-layer-maintenance/
│   ├── intent-layer-onboarding/
│   └── intent-layer-query/
├── agents/                   # Specialized subagents
│   ├── explorer.md
│   ├── validator.md
│   └── auditor.md
├── hooks/
│   └── hooks.json            # PostToolUse hook config
├── scripts/                  # Shared bash scripts
└── references/               # Templates and guides
```

## Script Features

All scripts support:
- `-h` / `--help` for usage information
- `set -euo pipefail` for robust error handling
- Cross-platform compatibility (macOS + Linux)
- Detailed error messages with remediation hints
- Consistent exclusion of generated directories (node_modules, dist, etc.)

## When to Use

### intent-layer

**Good for:**
- New projects that will be touched by AI agents
- Existing codebases where agents struggle to navigate
- Monorepos with complex subsystem boundaries
- Codebases with non-obvious contracts or invariants

**Not good for:**
- Tiny scripts or single-file projects
- Projects that change so rapidly the docs would be stale immediately
- Codebases you won't use AI agents on

### intent-layer-maintenance

**Good for:**
- Quarterly reviews of existing Intent Layers
- Post-incident updates (adding pitfalls, updating contracts)
- Post-refactor updates (moving entry points, changing boundaries)
- When agents consistently get confused about something

**Not good for:**
- Initial setup (use `intent-layer` first)
- Minor cosmetic changes that don't affect behavior
