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

### Global Pitfalls

- [Surprising behavior that catches people]

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

### Global Pitfalls

- [Non-obvious behavior that catches new contributors]

### Architecture Decisions

- [Decision 1]: `docs/adr/001.md`
- [Decision 2]: `docs/adr/002.md`
```

## Child Node Template (Agent-Optimized)

Each AGENTS.md in subdirectories. Optimized for AI agent consumption — every line must pass: "Would an agent fixing a bug here need this?"

**Token budget:** <1500 tokens (~1000 target)

```markdown
# {area_name}/

## Boundaries
- Imports from: [allowed dependencies]
- Does not import from: [prohibited dependencies]
- [Any isolation rules]

## Contracts
- [Invariant not enforced by types but must hold]
- [Data format assumption — e.g., "datetimes must be UTC-normalized"]
- [Pre/post condition on key function]

## Rules
- [Imperative sentence from git history or known failure mode]
- [WHEN condition] [ALWAYS/NEVER] [action]
- Test with: [targeted test command with specific file + flag]

## Ownership
- [file.py]: [responsibility — only if non-obvious from filename]
- Start here for [common task]: `path/to/file`

## Downlinks
| Area | Node | Description |
|------|------|-------------|
| [Child area] | `./child/AGENTS.md` | [Brief description] |
```

### Section guidance

Focus on **what agents can't infer from code**:

| Section | What to include | What to skip |
|---------|-----------------|--------------|
| Boundaries | Import/dependency constraints, module isolation rules | Obvious dependencies (same-package imports) |
| Contracts | Non-type-enforced invariants. Should cite the bug or incident that proved them | Type-enforced rules, hypothetical invariants |
| Rules | Imperative sentences from fix/revert commits, targeted test commands. Git-mined real bugs >> code-reading guesses | Broad test commands (`make test`, `pytest`), style rules (linters handle this), vague warnings ("be careful") |
| Ownership | File-to-responsibility mapping, "start here for X" entries. Only non-obvious mappings | Obvious mappings (routes.ts → routes, config.ts → configuration) |
| Downlinks | All child AGENTS.md nodes with descriptions | Bare links without descriptions |

### Generation order

Populate in this order (easier → harder):

1. **Boundaries** (imports + module structure — mechanical analysis)
2. **Contracts** (code reading — invariants not in the type system)
3. **Ownership, Downlinks** (file structure — "start here for X")
4. **Rules** (git/PR mining — needs judgment). Mine git history first, then supplement with code reading. Real bugs > hypothetical gotchas

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

## Maintenance Discipline

- **Quarterly review**: Review each node; keep only 2-5 highest-value items per section.
- **Mistake-driven growth**: New Rules/Contracts entries must come from real failures, not speculation. Git-mined bugs and PR discussions are the best sources. A contract without a failure story is just a guess.
- **Prune aggressively**: Remove items that are no longer relevant or have been fixed. Remove Rules that linters now enforce. Remove Ownership entries where filename = responsibility.
- **Evidence required**: Each Rule and Contract entry should reference a commit, PR, migration, or incident that justifies it. Entries without evidence are candidates for pruning.
- **Node quality > node count**: Don't create nodes for low-complexity directories (<5 source files, <2k tokens). A 54-line AGENTS.md for 4 markdown files is filler, not documentation.

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

## Cross-Tool Compatibility

The AGENTS.md standard is used by 20k+ projects across AI tools (Cursor, Copilot, Gemini CLI). For maximum compatibility:

```bash
# If your project uses CLAUDE.md as root, create a symlink for other tools:
ln -s CLAUDE.md AGENTS.md

# Or vice versa if you prefer AGENTS.md as primary:
ln -s AGENTS.md CLAUDE.md
```

Child nodes should always be named `AGENTS.md` (not CLAUDE.md) for cross-tool compatibility.
