# Onboarding Workflow

Quick reference for orienting newcomers using an existing Intent Layer. Previously the standalone `/intent-layer-onboarding` skill.

## Prerequisites

- Intent Layer state must be `complete`
- Run `show_hierarchy.sh` to visualize structure

## The 15-Minute Orientation

1. **Read root node** (2 min) — TL;DR, Subsystem Boundaries, Contracts, Pitfalls
2. **Map hierarchy** (2 min) — `show_hierarchy.sh`, note depth and complexity
3. **Identify entry point** (3 min) — match role/task to subsystem AGENTS.md
4. **Deep-read your area** (5 min) — Entry Points, Contracts, Pitfalls
5. **Verify understanding** (3 min) — can you explain, navigate, comply, avoid, start?

## Role-Based Entry Points

| Role | Start With |
|------|-----------|
| Frontend | UI/components AGENTS.md |
| Backend | API/services AGENTS.md |
| DevOps | Infrastructure AGENTS.md |
| Full-stack | Root + busiest subsystem |

## Task-Based Entry Points

| Task | Flow |
|------|------|
| Fix bug in X | Find nearest AGENTS.md → Pitfalls → Contracts → Entry Point |
| Add feature to Y | Find AGENTS.md → check scope → Entry Points → Contracts → parent constraints |
| Understand Z | Find AGENTS.md → TL;DR → Architecture Decisions → Entry Points → ancestors |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `generate_orientation.sh` | Create onboarding documents |
| `show_hierarchy.sh` | Visualize Intent Layer structure |
| `show_status.sh` | Check Intent Layer health |
| `query_intent.sh` | Search for specific concepts |
| `walk_ancestors.sh` | Gather context from hierarchy |

## Verification Checklist

After onboarding, the newcomer should be able to:
1. Explain the project in one sentence
2. Find the right AGENTS.md for any task
3. Know constraints that apply to their area
4. Know common pitfalls in their area
5. Know which file to open first
