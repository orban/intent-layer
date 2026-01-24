# Agent-Driven Capture Workflow

Iterative agent-human dialog for capturing tribal knowledge. More thorough than template-based capture.

## When to Use

- Initial capture for new Intent Nodes
- Major refactors requiring node rewrites
- When template-based capture (`capture_pain_points.sh`) feels insufficient
- Complex subsystems with deep tribal knowledge

## The Three Phases

```
┌─────────────────────────────────────────────────────────┐
│  Phase 1: Agent Analysis                                │
│  Agent examines code, proposes descriptions, asks Qs    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 2: Human Response                                │
│  Human corrects, answers, adds historical context       │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 3: Iterate                                       │
│  Repeat until description matches mental model          │
└─────────────────────────────────────────────────────────┘
```

## Phase 1: Agent Analysis

Agent examines the code chunk and produces:

### Observed Responsibilities
"Based on the code, this area appears to handle..."

### Detected Patterns
"I see a pattern where all X go through Y before Z..."

### Potential Contracts (inferred)
"It seems like an invariant that all database calls must..."

### Questions About Ambiguous Areas
"I found `legacy/converter.py` imported by 3 files but marked deprecated. Is this dead code?"

## Phase 2: Human Response

Human provides:

### Corrections
"Actually, that's not the main responsibility. The real purpose is..."

### Answers to Questions
"No, that's not dead code - it handles edge cases for pre-2023 accounts"

### Historical Context
"We chose this approach because at the time, the alternative wasn't available..."

### Known Landmines
"There's a gotcha here: if you delete that file, the import pipeline breaks silently"

## Phase 3: Iterate

Continue until:
- Agent's description matches human's mental model
- All blocking questions resolved
- Open questions parked with clear ownership

## Parking Unresolved Items

During capture, some items cannot be resolved immediately. Use `scripts/capture_state.sh` to generate a tracking template.

| Item Type | Action |
|-----------|--------|
| Open question | Park until neighbor nodes provide answer |
| Cross-reference | Track until LCA determined |
| Suspected dead code | Flag for human confirmation |
| Potential refactor | Note in shared state for backlog |

## Example Dialog

**Agent**: "I see `src/legacy/converter.py` is imported by 3 files but the functions are marked deprecated. Is this dead code?"

**Human**: "No - it handles edge cases for accounts created before 2023. The deprecation markers were premature."

**Agent**: "Should I add this to Pitfalls? 'legacy/converter.py looks deprecated but handles pre-2023 account edge cases'"

**Human**: "Yes, and also note that deleting it breaks the import pipeline silently."

**Agent**: "Updated Pitfalls:
- `legacy/converter.py` looks deprecated but handles pre-2023 account edge cases. Deleting breaks import pipeline silently.

I also noticed all API handlers go through `middleware/auth.ts`. Is this a contract I should document?"

**Human**: "Yes, that's a hard invariant. All public endpoints must go through that middleware - no exceptions."

**Agent**: "Adding to Contracts:
- All public API endpoints must route through `middleware/auth.ts`

Should I also note what happens if this is bypassed?"

**Human**: "Good idea - bypassing it means the request won't have user context, and downstream calls will fail with cryptic null pointer errors."

## Capture Order (Leaf-First)

1. **Well-understood leaf areas** (utilities, helpers)
2. **Domain-specific modules** (auth, payments, users)
3. **Integration layers** (APIs, clients)
4. **Complex/tangled areas** (legacy code)
5. **Root and intermediate nodes** (summarize children)

**Why leaf-first**: Clarity compounds. Earlier nodes make adjacent captures easier. Parent nodes summarize children, so children must exist first.

## Quality Checklist

Before finalizing an agent-captured node:

- [ ] Human confirmed all major observations
- [ ] All blocking questions answered
- [ ] Open questions parked with ownership
- [ ] Contracts stated explicitly (not "handle carefully")
- [ ] Pitfalls include what breaks and how
- [ ] Under 4k tokens
- [ ] No duplication with ancestor nodes

## Comparison: Template vs Agent-Driven

| Aspect | Template (`capture_pain_points.sh`) | Agent-Driven |
|--------|-------------------------------------|--------------|
| Speed | Fast (fill in blanks) | Slower (dialog) |
| Depth | Surface-level | Deep tribal knowledge |
| Questions | Pre-defined | Dynamic follow-ups |
| Best for | Quick audits, maintenance | Initial capture, complex areas |
| Human effort | Low | Medium |
| Coverage | What human remembers | What code + human know |

Use template-based for maintenance. Use agent-driven for initial capture of important nodes.
