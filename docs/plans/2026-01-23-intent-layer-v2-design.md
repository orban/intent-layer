# Intent Layer v2: Agent-Optimized Node Structure

> **Status:** Design approved, ready for implementation

## Summary

Enhance the Intent Layer node structure to include comprehensive codebase understanding beyond pitfalls and decisions. The new structure is optimized for AI agent consumption, prioritizing navigability and actionable context.

## Problem

The current Intent Layer captures:
- Purpose/TL;DR
- Entry Points
- Contracts & Invariants
- Patterns/Anti-patterns
- Pitfalls
- Boundaries (Always/Ask First/Never)
- Pre-flight Checks
- Architecture Decisions (links to ADRs)

**Missing:**
- Navigational code map ("where does X live?")
- Public API surface (what other modules depend on)
- Data flow for debugging
- Design rationale inline (ADRs often don't exist)
- External dependencies and their failure modes

## Solution

### Design Principles

1. **Agent-first** - Optimized for AI consumption, not human reading
2. **Navigational** - Answer "where does X live?" without exhaustive AST
3. **Self-contained** - Rationale inline, not links to non-existent ADRs
4. **Non-obvious focus** - Skip what agents can infer from file names/types
5. **Token-disciplined** - Stay under 4k tokens per node

### New Template Structure

```markdown
# {Area Name}

## Purpose
Owns: [what this area is responsible for]
Does not own: [explicitly out of scope - look elsewhere]

## Design Rationale
[Why this module exists and the philosophy behind it]

- **Problem solved**: [What pain point drove creation of this]
- **Core insight**: [The key idea that makes this work]
- **Constraints**: [What shaped the design]

## Code Map

### Find It Fast
| Looking for... | Go to |
|----------------|-------|
| [common search] | `path/to/file.ts` |
| [non-obvious location] | `path/file.ts` (not where you'd expect) |

### Key Relationships
- `layer1/` → `layer2/` → `layer3/` (direction matters)
- [Module A] imports from [Module B], never reverse

## Public API

### Key Exports
| Export | Used By | Change Impact |
|--------|---------|---------------|
| `functionName` | `consumer-module` | Breaking if signature changes |

### Core Types
```typescript
// The 3-5 types you need to understand to work here
interface KeyType { ... }
```

## External Dependencies
| Service | Used For | Failure Mode |
|---------|----------|--------------|
| [External service] | [Purpose] | [What happens when down] |

## Data Flow
```
Request → [validation] → [logic] → [data access] → Response
```

## Decisions
| Decision | Why | Rejected |
|----------|-----|----------|
| [Choice] | [Rationale] | [Alternative and why not] |

## Entry Points
| Task | Start Here |
|------|------------|
| [Common task] | `path/to/start.ts` |

## Contracts
- [Invariant not enforced by types but must hold]

## Patterns

### Adding a [common thing]
1. [Step with non-obvious detail]
2. [Step]

### Handling Errors
- Use `[ErrorType]` from `types/errors.ts`

## Pre-flight Checks

### Before [risky operation]
- [ ] [Verification - file exists, command passes, etc.]
- [ ] [Verification]

If any unchecked → [stop / fix first / ask user]

## Boundaries

### Always
- [Required practice]

### Never
- [Hard prohibition - consequence]

### Verify First
- [Risky operation] → confirm before proceeding

## Pitfalls
- `looks-wrong` is correct because [reason]
- `looks-fine` breaks [what] if you [action]

## Downlinks
| Area | Node | What's There |
|------|------|--------------|
| [Child] | `./child/AGENTS.md` | [Brief] |
```

### Token Budget

| Section | Target Tokens |
|---------|---------------|
| Purpose | ~50 |
| Design Rationale | ~200 |
| Code Map | ~400 |
| Public API | ~400 |
| External Dependencies | ~150 |
| Data Flow | ~150 |
| Decisions | ~400 |
| Entry Points | ~150 |
| Contracts | ~200 |
| Patterns | ~350 |
| Pre-flight Checks | ~150 |
| Boundaries | ~200 |
| Pitfalls | ~300 |
| Downlinks | ~100 |
| **Total** | **~3000** |

## Generation Guidance

### Section-by-Section

#### Purpose
- **Source:** Directory structure + main entry files
- **Question:** "What would break if this directory didn't exist?"
- **Compression:** One sentence each for "owns" and "doesn't own"

#### Code Map
- **Source:** `git log --name-only` for key files, `grep` for import relationships
- **Find It Fast:** Common searches from Slack, PRs, onboarding questions
- **Compression:** Only non-obvious locations

#### Public API
- **Source:** Export statements + imports from outside the directory
- **Core Types:** Types in function signatures of key exports
- **Compression:** Only exports used by OTHER modules

#### External Dependencies
- **Source:** SDK imports, `process.env` usage, config files
- **Failure Mode:** Check error handling or ask "what happens if down?"

#### Data Flow
- **Source:** Trace from entry point through function calls
- **Format:** Simple diagram or 2-3 sentences
- **Skip for:** Simple CRUD modules

#### Decisions
- **Source:** `mine_git_history.sh`, `mine_pr_reviews.sh`, team interviews
- **Question:** "Why this way and not the obvious other way?"
- **Compression:** Only decisions someone might question

#### Entry Points
- **Source:** Git log for frequently modified files, PR patterns
- **Question:** "If someone needs to do X, where do they start?"
- **Compression:** 5-7 most common tasks

#### Contracts
- **Source:** Assertions, validation patterns, "must/always" comments
- **Question:** "What would break silently if violated?"
- **Compression:** Only non-obvious invariants

#### Patterns
- **Source:** Existing similar code, PR review comments
- **Question:** "What steps do you repeat every time you add a [thing]?"
- **Compression:** Sequence + non-obvious steps only

#### Pre-flight Checks
- **Source:** Past mistakes, reverts, incident post-mortems
- **Question:** "What verification would have caught that mistake?"
- **When:** Only for genuinely risky operations

#### Boundaries
- **Source:** CI workflows, linting rules, incident history
- **Always:** Things CI should catch but doesn't
- **Never:** Things that cause incidents
- **Verify First:** "We've broken this before" operations

#### Pitfalls
- **Source:** Git blame, PR comments, onboarding confusion
- **Question:** "What surprised you when you first worked here?"
- **Gold standard:** Looks wrong but right, or looks right but wrong

#### Downlinks
- **Source:** `find [dir] -name "AGENTS.md"`
- **Compression:** One line per child

### Generation Order

Populate in this order (easier → harder):

1. Purpose - Quick orientation
2. Code Map - File system analysis
3. Public API - Export/import analysis
4. External Dependencies - Config/env analysis
5. Entry Points - Git log analysis
6. Downlinks - File system
7. Data Flow - Code reading
8. Contracts - Code reading + inference
9. Patterns - Existing examples
10. Boundaries - CI + team norms
11. Decisions - Git/PR mining (needs judgment)
12. Pitfalls - Git/PR mining + interviews (hardest)
13. Pre-flight Checks - Past mistakes (add over time)

## Changes from Current

| Aspect | Before | After |
|--------|--------|-------|
| Code navigation | Entry Points only | Code Map + Entry Points |
| Public API | Not documented | Key Exports + Core Types |
| Data flow | Not documented | Simple flow diagram |
| Decision rationale | Links to ADRs | Inline with rejected alternatives |
| External deps | Not documented | Service + failure mode |
| "Ask First" boundary | Included | Renamed to "Verify First" |

## Implementation Plan

1. Update `intent-layer/references/templates.md` with new template
2. Update `intent-layer/SKILL.md` to reference new sections
3. Add generation prompts to parallel exploration workflow
4. Test on a real codebase

## Risks

- **Token bloat** - Mitigated by strict budget per section
- **Generation complexity** - Mitigated by clear order and sources per section
- **Maintenance burden** - Same as before; Decisions/Pitfalls require judgment
