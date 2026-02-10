# Intent Layer Agent Protocol

> Specification for agent tools to consume and contribute to the Intent Layer.

## Version

Protocol version: 1.0

## Overview

The Intent Layer is a context protocol that lives in the filesystem alongside code.
Agents read AGENTS.md/CLAUDE.md files to understand intent, contracts, and pitfalls.
Agents write learning reports to feed discoveries back into the system.

## Filesystem Convention

### Node Files

| File | Location | Purpose |
|------|----------|---------|
| `CLAUDE.md` | Project root only | Root context node |
| `AGENTS.md` | Any subdirectory | Child context node |

Nodes form a tree following the directory hierarchy. A file at `src/api/AGENTS.md`
is a child of `src/AGENTS.md` (if it exists) or root `CLAUDE.md`.

### Required Sections (per node)

| Section | Content |
|---------|---------|
| `## Purpose` | What this directory owns and doesn't |
| `## Entry Points` | Task → file mappings |
| `## Contracts` | Non-type-enforced invariants |

### Optional Sections

| Section | When Present |
|---------|-------------|
| `## Pitfalls` | Known gotchas |
| `## Checks` | Pre-action verifications |
| `## Patterns` | Non-obvious workflows |
| `## Boundaries` | Always/Ask First/Never permissions |
| `## Design Rationale` | Why architecture exists |
| `## Code Map` | Non-obvious file locations |
| `## Public API` | Exports used by other modules |
| `## Downlinks` | Links to child nodes |

### Token Budget

Each node should be under 4,000 tokens (~3,000 target). Aim for 100:1 compression
ratio vs. reading the actual code.

## Reading Protocol (Context Resolution)

### Algorithm

To get context for a target path:

1. Walk up the directory tree from target to project root
2. Collect every `AGENTS.md` and `CLAUDE.md` encountered
3. Reverse to root-first order
4. Merge sections: child supplements parent (not replaces)

### T-Shaped Loading

Only load the vertical ancestor chain. Do NOT load sibling or cousin nodes:

```
CLAUDE.md (root)              ← LOAD
    ├── src/
    │   ├── AGENTS.md         ← LOAD (ancestor of target)
    │   ├── api/
    │   │   └── AGENTS.md     ← TARGET (load)
    │   └── auth/
    │       └── AGENTS.md     ← DO NOT load (sibling)
    └── tests/
        └── AGENTS.md         ← DO NOT load (uncle)
```

### Script Interface

```bash
resolve_context.sh <project_root> <target_path> [options]

Options:
  --sections "Contracts,Pitfalls"   Filter to specific sections
  --compact                         Minimal output (no hierarchy info)
  --with-pending                    Include unreviewed learning reports
```

Returns: Markdown text to stdout. Exit code 0 = success, 1 = error (invalid args), 2 = no coverage.

### Integration Example (non-Claude tools)

Any tool can implement context resolution:

```python
# Pseudocode for Cursor/Copilot/Gemini integration
import os

def resolve_context(project_root, target_path):
    """Walk ancestors, merge AGENTS.md sections."""
    sections = {}
    current = os.path.dirname(target_path)

    nodes = []
    while True:
        for name in ['AGENTS.md', 'CLAUDE.md']:
            path = os.path.join(current, name)
            if os.path.exists(path):
                nodes.append(path)
                break
        if current == project_root:
            break
        current = os.path.dirname(current)

    nodes.reverse()  # root-first
    for node in nodes:
        for section in parse_sections(node):
            sections.setdefault(section.name, []).append(section.content)

    return merge_sections(sections)
```

## Writing Protocol (Learning Reports)

### When to Write

An agent should report a learning when it discovers:
- A gotcha that would catch future agents (type: pitfall)
- A verification that should be done before an action (type: check)
- A better approach than what's documented (type: pattern)
- Important context not captured in any node (type: insight)

### Report Format

Reports are markdown files in `.intent-layer/mistakes/pending/`:

```
.intent-layer/
└── mistakes/
    ├── pending/        ← New reports land here
    │   ├── PITFALL-2026-02-06-000123-4567.md
    │   └── INSIGHT-2026-02-06-000456-4568.md
    ├── integrated/     ← Accepted and merged into AGENTS.md
    └── rejected/       ← Reviewed and dismissed
```

Filename: `{TYPE}-{DATE}-{RANDOM}-{PID}.md`

### Script Interface

```bash
report_learning.sh \
  --project /path/to/repo \
  --path src/api/handlers.ts \
  --type pitfall \
  --title "Arrow functions in API module" \
  --detail "All handlers use arrow syntax, not function declarations" \
  --agent-id "swarm-worker-3"
```

Returns: Creation banner including report path on stdout.

### Report Lifecycle

```
Agent discovers learning
       │
       ▼
report_learning.sh creates report in pending/
       │
       ▼
Human reviews (accept / reject / defer)
       │
       ├── Accept → integrate_pitfall.sh merges into AGENTS.md
       │             Report moves to integrated/
       │
       ├── Reject → Report moves to rejected/
       │
       └── Defer  → Report stays in pending/
```

### Concurrency Safety

Multiple workers can write reports simultaneously. Each report gets a unique ID
from `{RANDOM}-{PID}`. No locking required.

Workers MUST NOT write directly to AGENTS.md files. Always use the pending queue.

## LCA Placement Rule

Facts that apply to multiple directories belong at their Lowest Common Ancestor:

| Fact | Relevant to | Place at |
|------|-------------|----------|
| "All endpoints require auth" | `api/v1/*`, `api/v2/*` | `api/AGENTS.md` |
| "Never commit .env" | All paths | Root `CLAUDE.md` |
| "Use idempotency keys" | `payments/`, `billing/` | Their common parent |

## Compatibility

This protocol is tool-agnostic. Any AI agent that can read files from the filesystem
can consume AGENTS.md nodes. The naming convention `AGENTS.md` is recognized by
Cursor, GitHub Copilot, Gemini CLI, and Claude Code.

For projects using `CLAUDE.md` as root, create a symlink for cross-tool compatibility:
```bash
ln -s CLAUDE.md AGENTS.md
```
