# Intent Layer Templates

## Root Context Templates

Choose based on project size:

### Small Project (≤5 areas, <50k tokens)

```markdown
## Intent Layer

> TL;DR: [One-line project description]. See Entry Points below.

### Entry Points

| Task | Start Here |
|------|------------|
| [Common task 1] | `path/to/file` |
| [Common task 2] | `path/to/file` |

### Downlinks

- `src/core/AGENTS.md` - [Brief description]
- `src/api/AGENTS.md` - [Brief description]

### Contracts

- [Key invariant 1]
- [Key invariant 2]

### Pitfalls

- [Surprising behavior that catches people]
```

### Medium Project (6-15 areas, 50-150k tokens)

```markdown
## Intent Layer

> TL;DR: [One-line description]. Start at Entry Points, check Subsystems for deep dives.

### Subsystems

| Area | Location | Description |
|------|----------|-------------|
| [Area 1] | `path/AGENTS.md` | Brief description |
| [Area 2] | `path/AGENTS.md` | Brief description |
| [Area 3] | `path/AGENTS.md` | Brief description |

### Downlinks

| Area | Node | Description |
|------|------|-------------|
| API | `src/api/AGENTS.md` | REST endpoints |
| Core | `src/core/AGENTS.md` | Business logic |
| Data | `src/data/AGENTS.md` | Database layer |

### Entry Points

| Task | Start Here |
|------|------------|
| [Common task] | `path/` |

### Global Invariants

- [Invariant across all areas]

### Boundaries

#### Never
- [Project-wide prohibition]
```

### Large Project (>15 areas, >150k tokens or monorepo)

```markdown
## Intent Layer

> TL;DR: [One-line description]. Find your area in Subsystems, then read its AGENTS.md.

**Before modifying code in a subdirectory, read its AGENTS.md first.**

### Subsystems

#### Core Services
| Service | Location | Owner |
|---------|----------|-------|
| [Service 1] | `services/x/AGENTS.md` | @team-a |
| [Service 2] | `services/y/AGENTS.md` | @team-b |

#### Shared Libraries
| Library | Location | Description |
|---------|----------|-------------|
| [Lib 1] | `packages/x/AGENTS.md` | Shared utilities |

#### Infrastructure
| Component | Location |
|-----------|----------|
| [Infra 1] | `infra/AGENTS.md` |

### Downlinks

| Area | Node | Description |
|------|------|-------------|
| API Gateway | `services/gateway/AGENTS.md` | Request routing, rate limiting |
| User Service | `services/users/AGENTS.md` | Authentication, profiles |
| Payment Service | `services/payments/AGENTS.md` | Billing, transactions |
| Shared Utils | `packages/shared/AGENTS.md` | Common utilities |

### Cross-Cutting Concerns

- **Logging**: All services use `@org/logger` - see `packages/logger/AGENTS.md`
- **Auth**: JWT via `@org/auth` - never implement custom auth
- **Config**: Environment vars via `@org/config` - no direct `process.env`

### Global Pre-flight Checks

<!-- Checks that apply regardless of which subsystem is modified -->

#### Deployments
Before deploying any service:
- [ ] All tests pass in CI
- [ ] CHANGELOG.md updated
- [ ] No open P0 incidents

If any unchecked → stop and escalate to #releases.

### Global Invariants

- [Invariant 1]
- [Invariant 2]

### Architecture Decisions

- [Decision 1]: `docs/adr/001.md`
- [Decision 2]: `docs/adr/002.md`
```

## Child Node Template (Agent-Optimized)

Each AGENTS.md in subdirectories. Optimized for AI agent consumption - prioritizes navigability and actionable context.

**Token budget:** <4k tokens total (~3k target)

```markdown
# {Area Name}

## Purpose
Owns: [what this area is responsible for]
Does not own: [explicitly out of scope - look elsewhere for this]

## Design Rationale
[Why this module exists and the philosophy behind it]

- **Problem solved**: [What pain point or need drove creation of this]
- **Core insight**: [The key idea that makes this work - what you'd lose if you removed it]
- **Constraints**: [What shaped the design - performance, compatibility, team size, etc.]

## Code Map

### Find It Fast
| Looking for... | Go to |
|----------------|-------|
| [common search] | `path/to/file.ts` |
| [non-obvious location] | `path/file.ts` (not where you'd expect) |

### Key Relationships
- `layer1/` → `layer2/` → `layer3/` (direction matters, never skip)
- [Module A] imports from [Module B], never reverse

## Public API

### Key Exports
| Export | Used By | Change Impact |
|--------|---------|---------------|
| `functionName` | `consumer-module` | Breaking if signature changes |
| `TypeName` | Multiple modules | Widely depended on |

### Core Types
```typescript
// The 3-5 types you need to understand to work here
interface KeyType { ... }
type ImportantEnum = 'A' | 'B' | 'C'
```

## External Dependencies
| Service | Used For | Failure Mode |
|---------|----------|--------------|
| [Service name] | [Purpose] | [What happens when down] |

## Data Flow
```
Request → [validation] → [business logic] → [data access] → Response
                ↓ on error
           [error handler] → [logging] → Error Response
```

## Decisions
| Decision | Why | Rejected |
|----------|-----|----------|
| [Architectural choice] | [Rationale] | [Alternative and why not] |

## Entry Points
| Task | Start Here |
|------|------------|
| [Common task 1] | `path/to/start.ts` |
| [Common task 2] | `path/to/other.ts` |

## Contracts
- [Invariant not enforced by types but must hold]
- [Non-obvious rule] (reason: inline rationale)

## Patterns

### Adding a [common thing]
1. [Step with non-obvious detail]
2. [Step]
3. [Step - often-missed part]

### Handling Errors
- Use `[ErrorType]` from `types/errors.ts`
- [How errors flow up]

## Pre-flight Checks

<!-- Only for genuinely risky operations. Must be verifiable. -->

### Before [risky operation]
- [ ] [Verification - file exists, command passes, content matches]
- [ ] [Verification]

If any unchecked → [stop / fix first / ask user]

## Boundaries

### Always
- [Required practice - with brief why if non-obvious]

### Never
- [Hard prohibition - consequence if violated]

### Verify First
- [Risky operation] → confirm with user before proceeding

## Pitfalls
- `looks-wrong` is actually correct because [reason]
- `looks-fine` will break [what] if you [action]
- [Config/flag] is misleading - it actually controls [real behavior]

## Downlinks
| Area | Node | What's There |
|------|------|--------------|
| [Child area] | `./child/AGENTS.md` | [Brief description] |
```

### Section Guidance

When populating sections, focus on **what agents can't infer from code**:

| Section | What to Include | What to Skip |
|---------|-----------------|--------------|
| Design Rationale | Why this exists, core insight, constraints | Implementation details |
| Code Map | Non-obvious locations, semantic groupings | Obvious mappings (routes.ts → routes) |
| Public API | Exports used by OTHER modules | Internal-only exports |
| Decisions | Choices someone might question | Obvious decisions |
| Contracts | Non-type-enforced invariants | Type-enforced rules |
| Patterns | Sequence + non-obvious steps | "Create file, add imports" |
| Pitfalls | Looks wrong but right, or vice versa | Obvious gotchas |

### Generation Order

Populate sections in this order (easier → harder):

1. Purpose, Code Map, Public API (file system + imports)
2. External Dependencies, Entry Points, Downlinks (config + git log)
3. Data Flow, Contracts (code reading)
4. Patterns, Boundaries (existing examples + CI)
5. Decisions, Pitfalls (git/PR mining - needs judgment)
6. Design Rationale (requires understanding the "why" - often from interviews or deep history)
7. Pre-flight Checks (add over time from mistakes)

## Spec Templates (Greenfield)

Use these when NO code exists yet. Specs become documentation as code is built.

### Spec Root Template

```markdown
## Intent Layer (Spec)

> **Vision**: [What this project will become - one sentence]

### Planned Subsystems

| Subsystem | Responsibility | Priority |
|-----------|---------------|----------|
| [Name] | [What it will own] | P0/P1/P2 |

### Design Constraints

These MUST be true in the final implementation:
- [Constraint 1 - e.g., "All API responses under 100ms"]
- [Constraint 2 - e.g., "No direct database access from handlers"]

### Implementation Targets

Where to start building:
| Order | Target | Why First |
|-------|--------|-----------|
| 1 | [Component] | [Reason - e.g., "unblocks other work"] |
| 2 | [Component] | [Reason] |

### Open Questions

Resolve before building:
- [ ] [Question 1]
- [ ] [Question 2]

### Boundaries

#### Always
- [Required practice - e.g., "Test coverage >80%"]

#### Never
- [Prohibited approach - e.g., "No ORM, raw SQL only"]
```

### Spec Component Template

```markdown
# {Component Name} (Spec)

## Responsibility Charter

This component WILL own:
- [Responsibility 1]
- [Responsibility 2]

This component will NOT own:
- [Explicitly excluded responsibility]

## Interface Contracts

Other components will interact via:
```typescript
// Expected interface shape
interface {ComponentName}Service {
  method(input: Type): Promise<Result>
}
```

## Dependencies

This will depend on:
- [Dependency 1] - for [purpose]

## Acceptance Criteria

Done when:
- [ ] [Criterion 1]
- [ ] [Criterion 2]

## Implementation Hints

For AI scaffolding:
- Directory structure: `src/{component}/`
- Key files: `index.ts`, `types.ts`, `service.ts`
- Test pattern: Co-located `*.test.ts` files

## Boundaries

### Always
- [Component-specific required practice]

### Never
- [Component-specific prohibition]
```

## Scaffolding Protocol

When AI encounters spec nodes (marked with "(Spec)" in title), it should:

### 1. Generate Structure
```
Planned Subsystems table → Create directories
├── src/
│   ├── {subsystem-1}/
│   ├── {subsystem-2}/
```

### 2. Create Interfaces First
Interface Contracts sections → TypeScript interfaces/types

### 3. Add Implementation Breadcrumbs
```typescript
// TODO: Implement per spec in src/api/AGENTS.md
// Contract: All responses must include requestId
export async function handler() {
  throw new Error('Not implemented')
}
```

### 4. Generate Test Fixtures
Acceptance Criteria → Test file stubs

### 5. Report Gaps
Surface any specs that can't be scaffolded:
- Missing dependency information
- Ambiguous interface definitions
- Conflicting constraints

## Measurements Table Format

```
| Directory        | Tokens | Threshold | Needs Node? |
|------------------|--------|-----------|-------------|
| src/components   | ~30k   | 20-64k    | YES (2-3k)  |
| src/pages        | ~22k   | 20-64k    | YES (2-3k)  |
| src/lib          | ~8k    | <20k      | NO          |
```

Thresholds:
- <20k tokens → No node needed
- 20-64k tokens → 2-3k token node
- >64k tokens → Split into child nodes

## Three-Tier Boundaries Pattern

Use this pattern instead of narrative anti-patterns. It's clearer and prevents destructive mistakes.

```markdown
## Boundaries

### Always
[Actions that must happen every time - validation, testing, logging]
- Run tests before committing
- Use the approved linter config
- Document public APIs

### Ask First
[Actions requiring coordination or approval before proceeding]
- Schema migrations
- Breaking API changes
- Adding new dependencies
- Modifying shared infrastructure

### Never
[Prohibited actions that cause damage or violate policy]
- Commit credentials or secrets
- Force push to protected branches
- Delete production data
- Bypass code review
```

**Why three tiers?**
- **Always**: Builds habits, catches issues early
- **Ask First**: Prevents conflicts without blocking work
- **Never**: Hard stops for truly dangerous actions

**Migration from Anti-patterns**: Move "Never do X" items to the `Never` section. Move "Be careful when Y" items to `Ask First`. This is more scannable than prose.

## Writing Pre-flight Checks

Pre-flight checks catch "I thought I understood" mistakes before they happen.

### When to Add a Check

| Signal | Add Check For |
|--------|---------------|
| Agent made a mistake | What verification would have caught it? |
| PR reviewer caught missing step | What should agent have verified? |
| New person got confused | What confirmation would have helped? |
| Incident occurred | What validation would have prevented it? |

### Check Quality Criteria

Before adding a check, verify:
- [ ] **Verifiable**: Agent can confirm pass/fail without human help
- [ ] **Specific**: Clear what passes vs. fails (no "code is clean")
- [ ] **Scoped**: Tied to specific operation, not "always do X"
- [ ] **Actionable**: Clear what to do when check fails

### Check vs. Pitfall

| Use **Pitfall** | Use **Pre-flight Check** |
|-----------------|--------------------------|
| Awareness is enough | Verification is needed |
| No specific trigger | Clear trigger operation |
| Can't be mechanically verified | Can be verified by command/inspection |

**Example**:
- Pitfall: "Legacy config looks deprecated but enterprise clients use it"
- Check: "Before modifying config schema → grep for enterprise references"

## Pre-flight Check Patterns

Use these patterns when writing checks:

| Type | Pattern | Example |
|------|---------|---------|
| **File exists** | `[path] exists` | `config/routes.yaml exists` |
| **Content match** | `grep -q "[pattern]" [file]` | `grep -q "rate_limit" config.yaml` |
| **Command succeeds** | `[command] passes` | `make lint passes` |
| **Comprehension** | State the N [items] from [section] | State the 3 invariants from Contracts |
| **Human gate** | Confirm with [person/channel] | Confirm with #platform before proceeding |

**Failure actions** (pick one per check group):
- `ask before proceeding` - Uncertainty, need guidance
- `fix first` - Known remediation, agent can resolve
- `stop and escalate` - Critical/irreversible, requires human

## Cross-Tool Compatibility

The AGENTS.md standard is used by 20k+ projects across AI tools (Cursor, Copilot, Gemini CLI). For maximum compatibility:

```bash
# If your project uses CLAUDE.md as root, create a symlink for other tools:
ln -s CLAUDE.md AGENTS.md

# Or vice versa if you prefer AGENTS.md as primary:
ln -s AGENTS.md CLAUDE.md
```

Child nodes should always be named `AGENTS.md` (not CLAUDE.md) for cross-tool compatibility.
