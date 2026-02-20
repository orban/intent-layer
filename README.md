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

### From GitHub (recommended)

```bash
# Add the marketplace
/plugin marketplace add orban/intent-layer

# Install the plugin
/plugin install intent-layer@orban
```

Or using the CLI:

```bash
claude plugin marketplace add orban/intent-layer
claude plugin install intent-layer@orban
```

### From local directory

```bash
# Clone the repository
git clone https://github.com/orban/intent-layer.git

# Install from local path
claude plugin install ./intent-layer
```

## Components

### Skills

Interactive workflows invoked via slash commands:

| Skill | Purpose | Command |
|-------|---------|---------|
| `intent-layer` | Smart router: detects state, routes to setup/maintain/review | `/intent-layer` |
| `intent-layer:maintain` | Maintain existing Intent Layers | `/intent-layer:maintain` |
| `intent-layer:review` | Batch triage of pending learnings | `/intent-layer:review` |
| `intent-layer:query` | Query Intent Layer for answers | `/intent-layer:query` |
| `intent-layer:health` | Quick health check (validation + staleness + coverage) | `/intent-layer:health` |

### Agents

Specialized subagents that Claude invokes automatically when appropriate:

| Agent | Purpose |
|-------|---------|
| `explorer` | Analyze directories and propose AGENTS.md content |
| `validator` | Deep validation that nodes accurately reflect codebase |
| `auditor` | Find drift between nodes and current code state |

### Hooks

Automatic event handlers that keep the Intent Layer active during development:

| Hook | Event | Purpose |
|------|-------|---------|
| `post-edit-check` | PostToolUse | Remind about Intent Layer coverage after edits |
| `pre-edit-check` | PreToolUse | Inject pitfalls before edits, warn about uncovered dirs |
| `inject-learnings` | SessionStart | Inject recent learnings, suggest setup if no Intent Layer |
| `capture-tool-failure` | PostToolUseFailure | Auto-create skeleton mistake reports on Edit/Write failures |
| Stop prompt | Stop | LLM evaluates session for learnings to capture |

### Learning Loop

The plugin implements a continuous, mostly-automated learning loop:

```
Agent makes mistake → PostToolUseFailure auto-creates skeleton
                              ↓
                      Skeleton in .intent-layer/mistakes/pending/
                              ↓
                      Stop hook evaluates: enrich or discard?
                              ↓
                      Next session: Agent offers interactive review
                      or user runs /intent-layer:review
                              ↓
                      User decides: Accept / Reject / Discard
                              ↓ (on accept)
                      Auto-integrated via lib/integrate_pitfall.sh
                      Pitfall added to covering AGENTS.md
                              ↓
                      Next session: SessionStart injects learnings
                              ↓
                      PreToolUse injects relevant pitfalls before edits
```

**Interactive review**: When pending reports exist, the agent offers to walk you through them conversationally. You can also explicitly run `/intent-layer:review` to start a review session.

**Supporting scripts:**

| Script | Purpose |
|--------|---------|
| `lib/integrate_pitfall.sh` | Auto-add pitfalls to covering AGENTS.md |
| `scripts/capture_mistake.sh` | Manual capture (if auto-capture missed something) |
| `scripts/review_mistakes.sh` | Terminal-based review (alternative to agent) |

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
# In Claude Code: /intent-layer:maintain /path/to/project
```

### Onboarding

```bash
# Generate orientation overview
./scripts/generate_orientation.sh /path/to/project

# Or use the router which includes onboarding as an option
# In Claude Code: /intent-layer /path/to/project
```

## Plugin Structure

```
intent-layer-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/                   # Slash-command skills
│   ├── intent-layer/         # Smart router + sub-skills
│   │   └── workflows/        # Reference docs for flows
│   ├── intent-layer-maintain/
│   ├── intent-layer-review/
│   ├── intent-layer-query/
│   └── intent-layer-health/
├── agents/                   # Specialized subagents
│   ├── explorer.md
│   ├── validator.md
│   ├── auditor.md
│   └── change-tracker.md
├── hooks/
│   └── hooks.json            # 5 hook slots
├── scripts/                  # Shared bash scripts
├── lib/                      # Internal library scripts
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

### intent-layer:maintain

**Good for:**
- Quarterly reviews of existing Intent Layers
- Post-incident updates (adding pitfalls, updating contracts)
- Post-refactor updates (moving entry points, changing boundaries)
- When agents consistently get confused about something

**Not good for:**
- Initial setup (use `/intent-layer` first — it routes automatically)
- Minor cosmetic changes that don't affect behavior

## CI Integration

The plugin includes `detect_staleness.sh` for automated staleness checks in CI pipelines. The script exits with code 2 when stale nodes are found, making it easy to fail builds or create warnings.

### GitHub Actions

```yaml
# .github/workflows/intent-layer.yml
name: Intent Layer Check

on:
  pull_request:
  push:
    branches: [main]

jobs:
  staleness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Needed for git history analysis

      - name: Check Intent Layer staleness
        run: |
          ./scripts/detect_staleness.sh --code-changes --threshold 30
        continue-on-error: true  # Warning only, or remove for hard fail
```

### GitLab CI

```yaml
# .gitlab-ci.yml
intent-layer:check:
  stage: test
  script:
    - ./scripts/detect_staleness.sh --code-changes
  allow_failure: true  # Warning only
  only:
    - merge_requests
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No stale nodes found |
| 1 | Error (invalid path, etc.) |
| 2 | Stale nodes found |

### Useful Options

- `--code-changes`: Flag nodes where code changed more recently than the node
- `--threshold N`: Days since node update to consider stale (default: 90)
- `--quiet`: Output only paths (useful for scripting)

### PR Review Integration

For PR-specific checks, use `review_pr.sh` which validates changes against Intent Layer contracts:

```yaml
- name: Review PR against Intent Layer
  if: github.event_name == 'pull_request'
  run: |
    ./scripts/review_pr.sh origin/${{ github.base_ref }} HEAD
```
