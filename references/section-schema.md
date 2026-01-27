# Intent Layer Section Schema

Formal specification for AGENTS.md/CLAUDE.md sections. Use this to determine which sections your node needs and how to write them.

## Section Classification

### Mandatory Sections

Every valid node MUST have these three sections:

| Section | Purpose | Without It |
|---------|---------|------------|
| Purpose | What this directory owns and doesn't | Agent can't scope its work |
| Entry Points | Task → file mappings for common operations | Agent guesses where to start |
| Contracts | Non-type-enforced invariants, constraints | Agent violates invisible rules |

### Conditional Sections

Add when applicable (see Decision Tree below):

| Section | When to Add |
|---------|-------------|
| Design Rationale | Architecture is non-obvious or frequently questioned |
| Code Map | Directory structure doesn't match semantics |
| Public API | Exports are used by other modules |
| Patterns | Workflows differ from industry standard |
| Pitfalls | Mistakes have occurred and been documented |
| Boundaries | Permission structure is complex (Always/Ask First/Never) |
| Checks | Risky operations need pre-verification |
| Downlinks | Child nodes exist |

---

## Section Specifications

### Purpose (MANDATORY)

**What belongs here**: Single statement of ownership + explicit exclusions.

**Good example**:
```markdown
## Purpose
Owns: Payment lifecycle from initiation through settlement.
Does not own: Invoicing (see `billing/`), refunds (see `refunds/`).
```

**Bad example**:
```markdown
## Purpose
This module is responsible for handling various payment-related operations
and integrating with our payment processor. It's a critical part of our
infrastructure that many teams depend on.
```
*Problem*: Vague, no exclusions, no ownership boundaries.

**Size guidance**: 2-4 lines max. If longer, scope is too broad—split into child nodes.

**Relationship to other sections**: Purpose scopes everything else. Entry Points and Contracts exist within these boundaries.

---

### Entry Points (MANDATORY)

**What belongs here**: Task → file mappings for the 3-7 most common operations.

**Good example**:
```markdown
## Entry Points
| Task | Start Here |
|------|------------|
| Add payment method | `src/methods/` → implement interface |
| Debug failed charge | `src/handlers/charge.ts` → check logs |
| Modify validation | `src/validators/payment-validator.ts` |
```

**Bad example**:
```markdown
## Entry Points
- `index.ts` - Main entry point
- `utils.ts` - Utility functions
- `types.ts` - Type definitions
- `config.ts` - Configuration
```
*Problem*: Lists files, not tasks. Doesn't help agent know where to start for a goal.

**Size guidance**: 3-7 entries. More than 7 suggests need for child nodes or Code Map section.

**Relationship to other sections**: Entry Points tell WHERE. Patterns tell HOW once you're there.

---

### Contracts (MANDATORY)

**What belongs here**: Invariants not enforced by types, responsibility bounds, constraints that break things silently if violated.

**Good example**:
```markdown
## Contracts
- All external API calls go through `src/clients/` (never direct fetch)
- Amounts stored as cents (integer), never floating point
- Idempotency key required for mutations (checked at runtime, not compile time)
```

**Bad example**:
```markdown
## Contracts
- Code should be clean and well-tested
- Follow best practices
- Handle errors appropriately
```
*Problem*: Not verifiable, not specific, doesn't prevent real mistakes.

**Size guidance**: 3-10 items. Group into subsections if >10 (e.g., "Data Contracts", "API Contracts").

**Relationship to other sections**: Contracts are rules. Pitfalls are what happens when rules are violated. Boundaries are permission-based rules.

---

### Design Rationale (CONDITIONAL)

**When to add**: Architecture is non-obvious, frequently questioned, or has rejected alternatives worth documenting.

**What belongs here**: Why this approach exists, core insight, constraints that shaped design.

**Good example**:
```markdown
## Design Rationale
- **Problem solved**: Rate limiting per-user without shared state across pods
- **Core insight**: Token bucket in Redis, not in-memory (survives restarts)
- **Rejected**: In-memory rate limiting (lost on deploy, inconsistent across pods)
```

**Bad example**:
```markdown
## Design Rationale
We use a service-oriented architecture because it allows for better
scalability and maintainability. Each service has its own database
following the database-per-service pattern. This is a well-established
pattern in microservices.
```
*Problem*: Describes standard patterns, doesn't explain THIS codebase's decisions.

**Size guidance**: 3-5 bullet points. Longer explanations go in ADRs, link to them.

**Relationship to other sections**: Explains WHY contracts and patterns exist.

---

### Code Map (CONDITIONAL)

**When to add**: Directory structure doesn't match semantic meaning, or "Find It Fast" mapping saves significant time.

**What belongs here**: Directory → semantic meaning, non-obvious file locations.

**Good example**:
```markdown
## Code Map
| Looking for... | Go to |
|----------------|-------|
| Request validation | `src/middleware/` (not `src/validators/`) |
| Database migrations | `db/versions/` (not `migrations/`) |
| Shared types | `src/types/shared.ts` (other type files are internal) |

### Key Relationships
- `handlers/` → `services/` → `repositories/` (never skip layers)
```

**Bad example**:
```markdown
## Code Map
- `src/` - Source code
- `tests/` - Test files
- `config/` - Configuration files
- `docs/` - Documentation
```
*Problem*: States the obvious. Agent can read directory names.

**Size guidance**: Only include non-obvious mappings. 3-8 entries typical.

**Relationship to other sections**: Complements Entry Points. Entry Points = task-based. Code Map = structure-based.

---

### Public API (CONDITIONAL)

**When to add**: This module has exports used by other modules (cross-module dependencies).

**What belongs here**: Key exports, who uses them, change impact.

**Good example**:
```markdown
## Public API
| Export | Used By | Change Impact |
|--------|---------|---------------|
| `PaymentClient` | `checkout/`, `billing/` | Breaking if constructor changes |
| `PaymentStatus` | 12+ modules | Widely depended, add only (never remove values) |
| `validateCard()` | `checkout/` only | Safe to modify with coordination |
```

**Bad example**:
```markdown
## Public API
This module exports the following functions:
- processPayment()
- refundPayment()
- getPaymentStatus()
- validatePaymentMethod()
- createPaymentIntent()
```
*Problem*: Lists exports without context. Doesn't help agent understand impact.

**Size guidance**: Focus on exports with >1 consumer or high change impact. Skip internal-only exports.

**Relationship to other sections**: Public API is WHAT you expose. Contracts are the RULES for using it.

---

### Patterns (CONDITIONAL)

**When to add**: Workflows are non-standard, or common tasks have non-obvious steps.

**What belongs here**: Step-by-step sequences for common operations with non-obvious details.

**Good example**:
```markdown
## Patterns

### Adding a New Payment Method
1. Add type to `src/types/payment-method.ts`
2. Implement adapter in `src/adapters/` (must extend `BaseAdapter`)
3. Register in `src/adapters/index.ts` (ORDER MATTERS - first match wins)
4. Add feature flag in `config/features.yaml`
```

**Bad example**:
```markdown
## Patterns

### Adding a New Component
1. Create a new file
2. Write the component code
3. Add tests
4. Export from index
```
*Problem*: Generic steps any developer knows. No non-obvious details.

**Size guidance**: 2-4 patterns per node. Each pattern 3-6 steps. More patterns → consider child nodes.

**Relationship to other sections**: Entry Points tell WHERE. Patterns tell HOW with the gotchas.

---

### Pitfalls (CONDITIONAL)

**When to add**: Mistakes have occurred and been documented, or code has surprising behavior.

**What belongs here**: Things that look wrong but are correct, things that look fine but break, misleading names/flags.

**Good example**:
```markdown
## Pitfalls
- `src/legacy/` looks deprecated but handles pre-2023 accounts (don't remove)
- `validateCard()` returns `true` for test cards in prod (intentional for QA)
- `config.timeout` is in SECONDS, not milliseconds (despite other timeouts)
```

**Bad example**:
```markdown
## Pitfalls
- Make sure to handle errors properly
- Don't forget to add tests
- Be careful with database migrations
```
*Problem*: Generic advice, not specific gotchas from this codebase.

**Size guidance**: Add as discovered. No upper limit, but if >10, consider grouping or moving to child nodes.

**Relationship to other sections**: Contracts are rules. Pitfalls are "even though X looks like Y, it's actually Z."

---

### Boundaries (CONDITIONAL)

**When to add**: Permission structure is complex, or there are risky operations that need explicit categorization.

**What belongs here**: Three-tier structure: Always (required), Ask First (needs approval), Never (prohibited).

**Good example**:
```markdown
## Boundaries

### Always
- Run `make lint` before committing
- Use `PaymentClient` for external API calls (never direct fetch)

### Ask First
- Schema migrations (coordinate with DBA)
- Adding new payment providers (needs security review)

### Never
- Store card numbers (use tokenization only)
- Bypass idempotency checks (causes duplicate charges)
```

**Bad example**:
```markdown
## Boundaries
Be careful when making changes to this area. Make sure to test thoroughly
and get approval for big changes. Don't break anything.
```
*Problem*: Prose instead of structured tiers. Nothing actionable.

**Size guidance**: 2-5 items per tier. Empty tiers can be omitted.

**Relationship to other sections**: Boundaries are permission-based. Contracts are invariant-based. Both are rules, different framing.

---

### Checks (CONDITIONAL)

**When to add**: Risky operations need verification before proceeding. Added after mistakes occur.

**What belongs here**: Pre-action verifications that are mechanically checkable.

**Good example**:
```markdown
## Checks

### Before Modifying Payment Flow
- [ ] `grep -q "enterprise" config/` returns no matches (enterprise config is separate)
- [ ] `make test-payments` passes
- [ ] Feature flag exists in `config/features.yaml`

If any unchecked → stop and ask in #payments.
```

**Bad example**:
```markdown
## Checks
- Make sure you understand the code
- Verify your changes work correctly
- Check with the team if unsure
```
*Problem*: Not mechanically verifiable. "Understand the code" isn't a pass/fail check.

**Size guidance**: 2-5 checks per operation. More checks → operation is too risky, consider automation.

**Relationship to other sections**: Checks are for RISKY operations. Contracts are ALWAYS true. Pitfalls are AWARENESS.

---

### Downlinks (CONDITIONAL)

**When to add**: Child AGENTS.md nodes exist.

**What belongs here**: Links to child nodes with brief descriptions.

**Good example**:
```markdown
## Downlinks
| Area | Node | What's There |
|------|------|--------------|
| Payment Methods | `./methods/AGENTS.md` | Adding/modifying payment types |
| Adapters | `./adapters/AGENTS.md` | External processor integration |
```

**Bad example**:
```markdown
## Downlinks
- `./methods/AGENTS.md`
- `./adapters/AGENTS.md`
- `./validators/AGENTS.md`
- `./utils/AGENTS.md`
```
*Problem*: No descriptions. Agent doesn't know which to read.

**Size guidance**: All child nodes should be listed. If >10, consider restructuring hierarchy.

**Relationship to other sections**: Downlinks point to WHERE more detail lives. Purpose defines the boundary for this level.

---

## Decision Tree

```
START: Does my directory need an AGENTS.md?
│
├─ Is directory >20k tokens of code?
│  └─ YES → Create node (continue below)
│  └─ NO → Skip unless semantic boundary
│
MANDATORY (always add):
├─ Purpose ✓
├─ Entry Points ✓
└─ Contracts ✓

CONDITIONAL (ask each question):
│
├─ Is architecture non-obvious or questioned?
│  └─ YES → Add Design Rationale
│
├─ Does directory structure ≠ semantic meaning?
│  └─ YES → Add Code Map
│
├─ Are exports used by other modules?
│  └─ YES → Add Public API
│
├─ Do workflows differ from standard patterns?
│  └─ YES → Add Patterns
│
├─ Have mistakes been made here?
│  └─ YES → Add Pitfalls
│
├─ Are there risky operations needing permission?
│  └─ YES → Add Boundaries
│
├─ Are there operations needing pre-verification?
│  └─ YES → Add Checks
│
└─ Do child AGENTS.md nodes exist?
   └─ YES → Add Downlinks
```

---

## Minimal Viable Node

The smallest valid AGENTS.md:

```markdown
# Auth Service

## Purpose
Owns: User authentication and session management.
Does not own: Authorization/permissions (see `authz/`), user profiles (see `users/`).

## Entry Points
| Task | Start Here |
|------|------------|
| Add auth provider | `src/providers/` |
| Debug login issues | `src/handlers/login.ts` |
| Modify token format | `src/tokens/jwt.ts` |

## Contracts
- All passwords hashed via `src/crypto/hash.ts` (never store plaintext)
- Sessions expire after 24h (enforced by Redis TTL, not code)
- OAuth tokens refreshed automatically (don't cache externally)
```

**Token count**: ~150 tokens

**Why this works**:
- Purpose: Clear ownership and exclusions
- Entry Points: 3 common tasks with specific files
- Contracts: 3 non-obvious rules that prevent mistakes

Add more sections only when they add value that these three don't cover.

---

## Anti-Patterns

### The Exhaustive Node
```markdown
## Code Map
- `src/` - Source code
- `src/index.ts` - Entry point
- `src/types.ts` - Types
- `src/utils.ts` - Utilities
...
```
*Problem*: Lists everything, highlights nothing. Agent could infer this from `ls`.

### The Aspirational Node
```markdown
## Contracts
- Code should be well-tested
- Follow clean code principles
- Document your changes
```
*Problem*: Not verifiable, not specific to this codebase.

### The Historical Node
```markdown
## Design Rationale
In Q3 2021, we decided to migrate from MySQL to PostgreSQL because
the team felt it would provide better JSON support. This was a
controversial decision at the time...
```
*Problem*: History lesson, not actionable context. Put this in an ADR if needed.

### The Duplicating Node
```markdown
## Contracts
- All API calls require authentication (also in parent node)
- Use snake_case for JSON fields (also in root CLAUDE.md)
```
*Problem*: Duplicates ancestor content. Use LCA placement instead.

---

## Validation Checklist

Before finalizing a node:

- [ ] Has all three mandatory sections (Purpose, Entry Points, Contracts)
- [ ] Purpose has both "Owns" and "Does not own"
- [ ] Entry Points are task-based, not file listings
- [ ] Contracts are specific and verifiable
- [ ] Conditional sections only added when applicable
- [ ] No duplication with ancestor nodes
- [ ] Under 4k tokens (under 3k preferred)
- [ ] Every sentence passes: "Would this prevent a real mistake?"
