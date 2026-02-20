# Maintenance Workflow

Quick reference for `/intent-layer:maintain` audit flow. See `skills/intent-layer-maintain/SKILL.md` for full details.

## Flow

1. `detect_state.sh` → must be `complete`; otherwise redirect to `/intent-layer`
2. `estimate_all_candidates.sh` → measure token growth
3. Flag directories >20k tokens as child node candidates
4. Ask pain point questions (pitfalls, contract violations, architecture changes)
5. Map findings to AGENTS.md sections
6. Present update proposal to user
7. Apply approved updates + validate

## Audit Types

| Trigger | Focus |
|---------|-------|
| Quarterly review | Full: tokens + all question categories |
| Post-incident | Pitfalls + Contracts that were violated |
| After refactor | Entry Points + Subsystem Boundaries |
| After new feature | Architecture Decisions + Patterns |

## Finding → Section Mapping

| Finding Type | Target Section |
|--------------|----------------|
| Surprising behavior | Pitfalls |
| "Never do X" rule | Anti-patterns |
| Must-be-true constraint | Contracts |
| Technical decision rationale | Architecture Decisions |
| New common task | Entry Points |
| New subsystem | Subsystem Boundaries |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `detect_state.sh` | Check state |
| `estimate_all_candidates.sh` | Measure all directories |
| `detect_changes.sh` | Find affected nodes on merge/PR |
| `detect_staleness.sh` | Find nodes needing updates |
| `validate_node.sh` | Validate after edits |
