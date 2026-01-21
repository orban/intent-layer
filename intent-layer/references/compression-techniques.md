# Compression Techniques

How to achieve 100:1 compression (200k tokens of code → 2k token node).

> Compression isn't loss—it's signal extraction. Remove noise, keep decisions.

## Quick Reference

| Technique | Before | After |
|-----------|--------|-------|
| Remove boilerplate | "This service is responsible for handling..." | "Handles X" |
| Use examples over lists | "Supports JSON, XML, CSV, Protobuf..." | "Supports JSON (see `formats/` for others)" |
| Delete tech stack descriptions | "Built with React 18, TypeScript 5.0..." | (delete entirely) |
| Replace explanations with links | "We use eventual consistency because..." | "Why eventual consistency: `docs/adr/004.md`" |
| Merge similar items | 5 similar anti-patterns | 1 pattern + "similarly for X, Y, Z" |

## The Three-Pass Method

### Pass 1: Delete
Remove everything that:
- Describes what the code already shows (tools aren't policy)
- Explains standard patterns (readers know how REST works)
- Lists technologies without explaining why they matter
- Uses filler phrases ("It's important to note that...")

### Pass 2: Compress
Transform remaining content:
- Paragraphs → bullet points
- Bullet lists → tables
- Explanations → examples
- Descriptions → links

### Pass 3: Verify
Ask: "Would a senior engineer need this?"
- If they'd figure it out from the code: delete
- If it's surprising or non-obvious: keep
- If it prevents a mistake: definitely keep

## Compression Patterns

### 1. Remove "Responsible for" Boilerplate

**Before (45 tokens):**
```markdown
## Purpose
The UserService is responsible for managing all user-related operations
including authentication, authorization, profile management, and user
preferences. It serves as the central point for all user data access.
```

**After (12 tokens):**
```markdown
## Purpose
User lifecycle: auth, profiles, preferences. Single source for user data.
```

### 2. Examples Over Exhaustive Lists

**Before (38 tokens):**
```markdown
Supported formats:
- JSON (application/json)
- XML (application/xml)
- CSV (text/csv)
- Protobuf (application/protobuf)
- MessagePack (application/msgpack)
- YAML (application/yaml)
```

**After (15 tokens):**
```markdown
Formats: JSON (default), XML, CSV, Protobuf. See `formats/` for full list.
```

### 3. Delete Tech Stack Descriptions

**Before (52 tokens):**
```markdown
## Technology Stack
- **Frontend**: React 18.2 with TypeScript 5.0
- **State Management**: Redux Toolkit with RTK Query
- **Styling**: Tailwind CSS 3.3
- **Testing**: Jest + React Testing Library
- **Build**: Vite 4.4
```

**After (0 tokens):**
Delete entirely. The `package.json` is the source of truth. Only mention tech choices if there's a non-obvious reason:

```markdown
## Architecture Decisions
- RTK Query over React Query: team familiarity, Redux already in use
```

### 4. Replace Explanations with Links

**Before (67 tokens):**
```markdown
## Why Eventual Consistency
We chose eventual consistency for the notification system because real-time
delivery isn't critical, and it allows us to handle spikes in traffic more
gracefully. The trade-off is that users might see slightly stale data for
up to 30 seconds, which is acceptable for notifications.
```

**After (12 tokens):**
```markdown
## Architecture Decisions
- Eventual consistency for notifications: `docs/adr/004-eventual-consistency.md`
```

### 5. Merge Similar Items

**Before (48 tokens):**
```markdown
## Anti-patterns
- Don't call the database directly; use the repository layer
- Don't call external APIs directly; use the client wrappers
- Don't access environment variables directly; use the config module
- Don't log directly; use the structured logger
- Don't throw raw errors; use the error factory
```

**After (18 tokens):**
```markdown
## Anti-patterns
- Never bypass abstraction layers (db→repo, api→client, env→config, logs→logger, errors→factory)
```

### 6. Tables Over Prose

**Before (89 tokens):**
```markdown
## Entry Points
The main entry point is `index.ts` which bootstraps the application. For API
requests, start at `routes.ts` which maps URLs to handlers. If you're working
on background jobs, look at `workers/index.ts`. Database migrations are in
`migrations/` and should be run with the CLI tool. Configuration is loaded
from `config.ts` which reads from environment variables.
```

**After (32 tokens):**
```markdown
## Entry Points
| Task | Start Here |
|------|------------|
| API changes | `routes.ts` → `handlers/` |
| Background jobs | `workers/index.ts` |
| DB changes | `migrations/` (use CLI) |
| Config | `config.ts` |
```

### 7. One-Liners for Single Concepts

**Before (34 tokens):**
```markdown
## Caching Strategy
We use Redis for caching with a default TTL of 5 minutes. Cache keys follow
the pattern `{service}:{entity}:{id}`. Invalidation happens automatically
on writes.
```

**After (14 tokens):**
```markdown
## Caching
Redis, 5min TTL, keys=`{service}:{entity}:{id}`, auto-invalidate on write.
```

## What to Keep vs. Delete

### Always Keep
- Contracts that aren't in the code (API guarantees, SLAs)
- Invariants that break things silently if violated
- Surprising behaviors that look like bugs but aren't
- Entry points that aren't obvious from file structure
- Patterns that differ from industry standard

### Always Delete
- Technology versions (they're in package files)
- Standard patterns explained (REST, MVC, etc.)
- Code comments repeated in docs
- Obvious file purposes (`utils/` contains utilities)
- Historical context nobody needs

### Keep If Non-Obvious
- Why a dependency was chosen over alternatives
- Why a pattern differs from team standard
- Performance constraints that affect design
- Security considerations that aren't enforced by code

## Compression Checklist

Before finalizing a node:

- [ ] Under 4k tokens (under 3k preferred)
- [ ] No "responsible for" or "this section describes"
- [ ] No tech stack lists without reasoning
- [ ] No lists > 5 items (use tables or "see X for full list")
- [ ] No explanations that belong in ADRs
- [ ] Every sentence passes "would senior engineer need this?"
- [ ] Links to details instead of inlining them

## Token Budget Guidelines

| Node Type | Target | Max |
|-----------|--------|-----|
| Root (monorepo) | 1-2k | 3k |
| Root (single project) | 500-1k | 2k |
| Child (major subsystem) | 1-2k | 3k |
| Child (focused module) | 300-800 | 1.5k |

Remember: If you're struggling to compress, the scope might be too broad. Consider splitting into child nodes instead.
