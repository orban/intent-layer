# Intent Layer Taxonomy

Unified conceptual model for distinguishing overloaded terminology.

> Terms like "Contract," "Pitfall," and "Pattern" each have multiple meanings in Intent Layer. This taxonomy eliminates ambiguity.

## Contract Taxonomy

Contracts define boundaries. Three distinct types:

### Runtime Contract

**Definition**: Invariants that must hold during program execution.

**When to use**: Document behaviors that aren't enforced by types but will break things silently if violated.

**Example**:
```markdown
## Contracts
- Auth tokens expire after 1 hour - refresh before making subsequent calls
- All API responses include `requestId` header for tracing
- Cache entries auto-invalidate on write - never manually invalidate
```

**Anti-example**: "POST /users accepts {name, email}" - This is an API Contract (interface shape), not a runtime invariant.

### API Contract

**Definition**: Interface shapes and type-level guarantees.

**When to use**: Document expected inputs/outputs, required fields, and type constraints.

**Example**:
```markdown
## Public API
| Export | Signature | Used By |
|--------|-----------|---------|
| `createUser` | `(input: CreateUserInput) => Promise<User>` | `auth-service` |
| `UserRole` | `'admin' \| 'member' \| 'guest'` | Multiple modules |
```

**Anti-example**: "Never call createUser without validation" - This is a Behavioral Pitfall, not an interface definition.

### Responsibility Contract

**Definition**: Ownership bounds defining what a module handles and explicitly excludes.

**When to use**: Prevent scope creep and clarify where functionality lives.

**Example**:
```markdown
## Purpose
Owns: user lifecycle (registration, auth, profile updates)
Does not own: billing (see `billing-service`), notifications (see `notifier`)
```

**Anti-example**: "Users must have valid email" - This is a Runtime Contract (data invariant), not an ownership boundary.

---

## Pitfall Taxonomy

Pitfalls prevent repeated mistakes. Three distinct types:

### Behavioral Pitfall

**Definition**: Code behavior that contradicts reasonable expectations (the "gotcha").

**When to use**: Document when something looks wrong but is correct, or looks fine but will break.

**Example**:
```markdown
## Pitfalls
- `src/legacy/` looks deprecated but handles edge cases for pre-2023 accounts
- `config.timeout = 0` means "no timeout", not "instant timeout"
- `user.active` can be `true` even when `user.suspended` is also `true`
```

**How it differs from others**:
- **vs Incident Insight**: Behavioral Pitfalls are inherent to the code design; Incident Insights are discovered during specific work
- **vs Anti-pattern**: Behavioral Pitfalls describe what IS; Anti-patterns describe what should NOT BE

### Incident Insight

**Definition**: Non-obvious error discovered during real work, captured via the learning loop.

**When to use**: Document mistakes that happened, so they don't happen again.

**Example**:
```markdown
## Pitfalls

### API response format varies
**Problem**: `parse_response()` assumes dict, but API can return list
**Symptom**: `'list' object has no attribute 'get'`
**Solution**: Check `isinstance(data, list)` before calling `.get()`
```

**How it differs from others**:
- **vs Behavioral Pitfall**: Incident Insights include problem/symptom/solution structure; Behavioral Pitfalls are one-liners about code quirks
- **vs Anti-pattern**: Incident Insights are reactive (learned from failure); Anti-patterns are proactive (team philosophy)

### Anti-pattern

**Definition**: Prohibited approach that violates team philosophy or causes known harm.

**When to use**: Document practices that must never occur, regardless of whether they'd "work."

**Example**:
```markdown
## Boundaries

### Never
- Import between services directly - use message queue
- Store card numbers - use tokenization only
- Bypass `processor-client.ts` for external calls
```

**How it differs from others**:
- **vs Behavioral Pitfall**: Anti-patterns are prohibitions; Behavioral Pitfalls are observations
- **vs Incident Insight**: Anti-patterns are policy; Incident Insights are experience

---

## Pattern Taxonomy

Patterns provide guidance. Three distinct types:

### Workflow Pattern

**Definition**: Step-by-step sequence for completing a common task.

**When to use**: Document multi-step processes where order matters or steps are non-obvious.

**Example**:
```markdown
## Patterns

### Adding a new payment method
1. Add type to `src/types/payment-method.ts`
2. Implement adapter in `src/adapters/`
3. Register in `src/adapters/index.ts`
4. Add feature flag in `config/features.yaml`
```

### Architectural Pattern

**Definition**: High-level structural approach that shapes code organization (not step-by-step).

**When to use**: Document how components relate, not how to perform tasks.

**Example**:
```markdown
## Architecture
- Services communicate via message queue, never direct HTTP
- Repository layer wraps all database access
- `handlers/` → `services/` → `repositories/` (never skip layers)
```

### Naming Pattern

**Definition**: Convention for identifiers, files, and variables.

**When to use**: Document naming rules that aren't enforced by linting.

**Example**:
```markdown
## Patterns
- Files: `kebab-case.ts` for modules, `PascalCase.ts` for classes
- Event names: `{entity}.{action}` (e.g., `user.created`, `payment.failed`)
- Cache keys: `{service}:{entity}:{id}` (e.g., `users:profile:123`)
```

---

## Decision Trees

### Is this a Contract, Pitfall, or Pattern?

```
Does it describe what MUST be true?
├─ YES → Does it define inputs/outputs and types?
│        ├─ YES → API Contract
│        └─ NO → Does it define ownership boundaries?
│                 ├─ YES → Responsibility Contract
│                 └─ NO → Runtime Contract
└─ NO → Does it describe something that goes wrong or surprises people?
        ├─ YES → Pitfall (see "What type of Pitfall?")
        └─ NO → Pattern (Workflow, Architectural, or Naming)
```

### What type of Contract is this?

```
What is being constrained?
├─ Data behavior at runtime (expiry, auto-invalidation, side effects)
│  → Runtime Contract
├─ Interface shape (function signatures, types, required fields)
│  → API Contract
└─ Module scope (what this owns vs. what lives elsewhere)
   → Responsibility Contract
```

### What type of Pitfall is this?

```
How was this discovered?
├─ It's inherent to how the code works (design quirk)
│  → Behavioral Pitfall
├─ Someone made a mistake and we learned from it
│  → Incident Insight (use problem/symptom/solution format)
└─ Team decided this approach is forbidden
   → Anti-pattern (goes in Boundaries > Never)
```

---

## Quick Reference Table

| Scenario | Taxonomy Term | Section |
|----------|---------------|---------|
| "Auth tokens expire after 1 hour" | Runtime Contract | Contracts |
| "POST /users accepts {name, email}" | API Contract | Public API |
| "We handle auth, billing-service handles invoices" | Responsibility Contract | Purpose |
| "`legacy/` looks deprecated but isn't" | Behavioral Pitfall | Pitfalls |
| "API returned list when we expected dict" | Incident Insight | Pitfalls |
| "Never import between services directly" | Anti-pattern | Boundaries > Never |
| "To add a payment method: 1. Add type..." | Workflow Pattern | Patterns |
| "Services communicate via queue, not HTTP" | Architectural Pattern | Architecture / Contracts |
| "Event names follow `{entity}.{action}`" | Naming Pattern | Patterns |
| "This module owns X but not Y" | Responsibility Contract | Purpose |
| "Cache auto-invalidates on write" | Runtime Contract | Contracts |
| "`timeout = 0` means no timeout" | Behavioral Pitfall | Pitfalls |
| "Don't store passwords directly" | Anti-pattern | Boundaries > Never |
| "Files use kebab-case.ts" | Naming Pattern | Patterns |
| "handlers → services → repos" | Architectural Pattern | Architecture |

---

## Common Misclassifications

| Often Misclassified As | Actually Is | Why |
|------------------------|-------------|-----|
| Contract: "Never call X directly" | Anti-pattern | Prohibition, not invariant |
| Pattern: "Don't use Y" | Anti-pattern | Describes what NOT to do |
| Pitfall: "Use Z instead of W" | Workflow Pattern | Prescribes correct approach |
| Contract: "X happens before Y" | Workflow Pattern | Sequence, not invariant |
| Pattern: "Auth tokens expire" | Runtime Contract | Statement of fact, not guidance |

---

## Placement Summary

| Type | Where It Goes |
|------|---------------|
| Runtime Contract | `## Contracts` section |
| API Contract | `## Public API` section |
| Responsibility Contract | `## Purpose` section |
| Behavioral Pitfall | `## Pitfalls` section |
| Incident Insight | `## Pitfalls` section (with problem/symptom/solution) |
| Anti-pattern | `## Boundaries > Never` section |
| Workflow Pattern | `## Patterns` section |
| Architectural Pattern | `## Architecture` or `## Contracts` section |
| Naming Pattern | `## Patterns` section |
