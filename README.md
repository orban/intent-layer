# Claude Code Skills

Custom skills for Claude Code CLI.

## Installation

Skills are symlinked to `~/.claude/skills/`:

```bash
ln -s ~/dev/claude-skills/intent-layer ~/.claude/skills/intent-layer
ln -s ~/dev/claude-skills/intent-layer-maintenance ~/.claude/skills/intent-layer-maintenance
```

## Skills

### intent-layer

Set up hierarchical Intent Layer (AGENTS.md/CLAUDE.md files) for codebases. Helps AI agents navigate codebases like senior engineers.

**Use when**: Initializing a new project, adding context infrastructure, setting up AGENTS.md.

### intent-layer-maintenance

Maintain existing Intent Layers through quarterly audits, pain point capture, and incremental updates.

**Use when**: Project already has state=complete, after incidents, after refactors.

## Structure

```
claude-skills/
├── intent-layer/
│   ├── SKILL.md              # Main skill documentation
│   ├── scripts/              # Automation scripts
│   │   ├── detect_state.sh
│   │   ├── analyze_structure.sh
│   │   ├── estimate_tokens.sh
│   │   ├── estimate_all_candidates.sh
│   │   ├── validate_node.sh
│   │   └── capture_pain_points.sh
│   └── references/           # Templates and guides
│       ├── templates.md
│       ├── node-examples.md
│       ├── capture-protocol.md
│       └── compression-techniques.md
│
└── intent-layer-maintenance/
    └── SKILL.md              # Maintenance workflow
```
