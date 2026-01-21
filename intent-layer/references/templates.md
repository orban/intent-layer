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

### Cross-Cutting Concerns

- **Logging**: All services use `@org/logger` - see `packages/logger/AGENTS.md`
- **Auth**: JWT via `@org/auth` - never implement custom auth
- **Config**: Environment vars via `@org/config` - no direct `process.env`

### Global Invariants

- [Invariant 1]
- [Invariant 2]

### Architecture Decisions

- [Decision 1]: `docs/adr/001.md`
- [Decision 2]: `docs/adr/002.md`
```

## Child Node Template

Each AGENTS.md in subdirectories:

```markdown
# {Area Name}

## Purpose
[1-2 sentences: what this area owns, what it explicitly doesn't do]

## Boundaries

### Always
- Run `make test` before committing changes to this area
- Use TypeScript strict mode for all new files
- Log errors to the structured logger, never console.log

### Ask First
- Database schema changes (coordinate with DBA)
- Changes to public API response shapes
- Adding new external dependencies

### Never
- Commit secrets, tokens, or .env files
- Push directly to main branch
- Delete user data without soft-delete

## Entry Points
- `main_api.ts` - Primary API surface
- `cli.ts` - CLI commands

## Contracts & Invariants
- All DB calls go through `./db/client.ts`
- Never import from `./internal/` outside this directory

## Patterns
To add a new endpoint:
1. Create handler in `./handlers/`
2. Register in `./routes.ts`
3. Add types to `./types.ts`

## Anti-patterns
- Never call external APIs directly; use `./clients/`
- Don't bypass validation layer

## Pitfalls
- `src/legacy/` looks deprecated but handles edge cases for pre-2023 accounts
- `useCache: true` in `config.ts` is misleading—it's actually required for prod
- The `async` flag in config is misleading—synchronous mode was removed in v2

## Architecture Decisions
- Why we use eventual consistency: `/docs/adrs/004-eventual-consistency.md`
- Payment flow diagram: `/docs/architecture/payment-flow.md`

## Related Context
- Database layer: `./db/AGENTS.md`
- Shared utilities: `../shared/AGENTS.md`
```

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

## Cross-Tool Compatibility

The AGENTS.md standard is used by 20k+ projects across AI tools (Cursor, Copilot, Gemini CLI). For maximum compatibility:

```bash
# If your project uses CLAUDE.md as root, create a symlink for other tools:
ln -s CLAUDE.md AGENTS.md

# Or vice versa if you prefer AGENTS.md as primary:
ln -s AGENTS.md CLAUDE.md
```

Child nodes should always be named `AGENTS.md` (not CLAUDE.md) for cross-tool compatibility.
