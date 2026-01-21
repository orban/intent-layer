# Claude Code Skills

Custom skills for Claude Code CLI.

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

## Installation

Skills are symlinked to `~/.claude/skills/`:

```bash
ln -s ~/dev/claude-skills/intent-layer ~/.claude/skills/intent-layer
ln -s ~/dev/claude-skills/intent-layer-maintenance ~/.claude/skills/intent-layer-maintenance
```

## Skills

### intent-layer

Set up hierarchical Intent Layer (AGENTS.md/CLAUDE.md files) for codebases. Helps AI agents navigate codebases like senior engineers.

```bash
# Check current state
./intent-layer/scripts/detect_state.sh /path/to/project

# Analyze token distribution
./intent-layer/scripts/estimate_all_candidates.sh /path/to/project

# Validate a node
./intent-layer/scripts/validate_node.sh CLAUDE.md
```

### intent-layer-maintenance

Maintain existing Intent Layers through quarterly audits, pain point capture, and incremental updates.

```bash
# Detect which nodes need review after changes
./intent-layer/scripts/detect_changes.sh main HEAD

# Generate pain point capture template
./intent-layer/scripts/capture_pain_points.sh pain_points.md
```

## Structure

```
claude-skills/
├── intent-layer/
│   ├── SKILL.md              # Main skill documentation
│   ├── scripts/              # Automation scripts (all support -h/--help)
│   │   ├── detect_state.sh
│   │   ├── analyze_structure.sh
│   │   ├── estimate_tokens.sh
│   │   ├── estimate_all_candidates.sh
│   │   ├── validate_node.sh
│   │   ├── capture_pain_points.sh
│   │   ├── capture_state.sh
│   │   └── detect_changes.sh
│   └── references/           # Templates and guides
│       ├── templates.md
│       ├── node-examples.md
│       ├── capture-protocol.md
│       ├── compression-techniques.md
│       ├── agent-feedback-protocol.md
│       └── capture-workflow-agent.md
│
└── intent-layer-maintenance/
    └── SKILL.md              # Maintenance workflow
```

## Script Features

All scripts support:
- `-h` / `--help` for usage information
- `set -euo pipefail` for robust error handling
- Cross-platform compatibility (macOS + Linux)
- Detailed error messages with remediation hints
- Consistent exclusion of generated directories (node_modules, dist, etc.)
