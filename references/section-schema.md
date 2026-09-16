# Intent Layer Section Schema

Agent-optimized schema for AGENTS.md/CLAUDE.md. Five sections, one mandatory. Every line must pass: "Would an agent fixing a bug here need this?"

## Section classification

### Mandatory

| Section | Purpose | Without it |
|---------|---------|------------|
| Contracts | Invariants not in the type system, pre/post conditions | Agent violates invisible rules |

### Conditional

| Section | When to add |
|---------|-------------|
| Boundaries | Module has import/dependency constraints or isolation rules |
| Rules | Git history reveals failure modes, gotchas, or targeted test commands |
| Ownership | File-to-responsibility mapping is non-obvious from directory names |
| Downlinks | Child AGENTS.md nodes exist |

---

## Section specifications

### Contracts (MANDATORY)

What belongs here: invariants not enforced by types, pre/post conditions, data format assumptions. These are the rules that break things silently when violated.

**Good:**
```markdown
## Contracts
- All datetime parameters must be UTC-normalized before comparison
- Edge lists can be empty — callers must handle zero-length
- Amounts stored as cents (integer), never floating point
- Idempotency key required for mutations (checked at runtime, not compile time)
```

**Bad:**
```markdown
## Contracts
- Code should be clean and well-tested
- Follow best practices
- Handle errors appropriately
```
*Problem*: Not verifiable, not specific to this codebase.

**Size:** 3-10 items. Group into subsections if >10.

---

### Boundaries (CONDITIONAL)

When to add: module has import/dependency constraints, isolation rules, or things that must never cross module boundaries.

What belongs here: allowed dependencies, import direction rules, isolation constraints.

**Good:**
```markdown
## Boundaries
- Imports from: graphiti_core.models
- Does not import from: graphiti_core.server, graphiti_core.driver
- Modules in plugins/ can only import from module_utils/
```

**Bad:**
```markdown
## Boundaries
Be careful when making changes. Get approval for big changes.
```
*Problem*: Prose instead of constraints. Nothing actionable.

**Size:** 2-8 items. If empty, omit the section.

---

### Rules (CONDITIONAL)

When to add: git history reveals failure modes, revert-worthy bugs, or non-obvious test commands. Merged from the old Pitfalls, Patterns, and Checks sections.

What belongs here: one imperative sentence per line. Sourced from fix/revert commits, known failure modes, targeted test commands.

Format: `[WHEN condition] [ALWAYS/NEVER] [action]` or plain imperative.

**Good:**
```markdown
## Rules
- Filter falsey values from edge lists before iteration
- API responses can be list or dict; check isinstance before .get()
- FalkorDB returns string IDs for numeric fields — cast before comparison
- Test with: pytest tests/unit/test_temporal.py -k test_utc
```

**Bad:**
```markdown
## Rules
- Follow PEP 8 style guidelines
- make test
- Be careful when modifying this code
- This is a critical component
```
*Problem*: Linters handle style. Broad test commands cause slow runs. "Be careful" is vague. "Critical" is puffery.

**MUST NOT** include broad commands like `make test`, `pytest`, `npm test`. Only targeted test commands with specific file + flag.

**Size:** 3-15 items. If >15, split into child nodes.

---

### Ownership (CONDITIONAL)

When to add: file-to-responsibility mapping is non-obvious from directory names. Includes "start here for X" entries.

What belongs here: file → responsibility mapping, entry points for common tasks. Only non-obvious mappings (skip if directory name = purpose).

**Good:**
```markdown
## Ownership
- temporal_utils.py: datetime normalization, timezone handling
- maintenance/: graph cleanup operations, bulk updates
- Start here for datetime bugs: temporal_utils.py
- Start here for adding payment methods: src/adapters/
```

**Bad:**
```markdown
## Ownership
- routes.ts: routes
- config.ts: configuration
- utils.ts: utilities
```
*Problem*: States the obvious. Agent can read filenames.

**Size:** 3-10 entries. If >10, directory needs child nodes.

---

### Downlinks (CONDITIONAL)

When to add: child AGENTS.md nodes exist below this directory.

What belongs here: one row per child node with brief description.

**Good:**
```markdown
## Downlinks
| Area | Node | Description |
|------|------|-------------|
| Payment Methods | `./methods/AGENTS.md` | Adding/modifying payment types |
| Adapters | `./adapters/AGENTS.md` | External processor integration |
```

**Bad:**
```markdown
## Downlinks
- `./methods/AGENTS.md`
- `./adapters/AGENTS.md`
```
*Problem*: No descriptions. Agent doesn't know which to read.

**Size:** All child nodes listed. If >10, consider restructuring hierarchy.

---

## Minimal viable node

The smallest valid AGENTS.md:

```markdown
# Auth Service

## Contracts
- All passwords hashed via `src/crypto/hash.ts` (never store plaintext)
- Sessions expire after 24h (enforced by Redis TTL, not code)
- OAuth tokens refreshed automatically (don't cache externally)
```

**Token count:** ~50 tokens

Add more sections only when they add value that Contracts alone doesn't cover.

---

## Decision tree

```
START: Does my directory need an AGENTS.md?
│
├─ Is directory >20k tokens of code?
│  └─ YES → Create node (continue below)
│  └─ NO → Skip unless semantic boundary
│
MANDATORY (always add):
└─ Contracts ✓

CONDITIONAL (ask each question):
│
├─ Does module have import/dependency constraints?
│  └─ YES → Add Boundaries
│
├─ Does git history reveal failure modes or gotchas?
│  └─ YES → Add Rules
│
├─ Is file-to-responsibility mapping non-obvious?
│  └─ YES → Add Ownership
│
└─ Do child AGENTS.md nodes exist?
   └─ YES → Add Downlinks
```

---

## What was dropped (and why)

| Old section | Why dropped |
|-------------|-------------|
| Purpose | One-line comment in heading suffices |
| Design Rationale | Narrative, not actionable for bug fixes |
| Code Map | Agents discover structure by reading files |
| Public API | IDEs/LSP handle this better |
| Entry Points | Merged into Ownership |
| Patterns | Merged into Rules (imperative form) |
| Pitfalls | Merged into Rules (imperative form) |
| Checks | Merged into Rules (targeted test commands) |
| External Dependencies | Rarely actionable for bug fixes |
| Data Flow | Narrative |

---

## Anti-patterns

### The narrative node
```markdown
This module handles utility functions for the project. It follows
a layered architecture pattern with clear separation of concerns.
```
*Problem*: Agent can't act on this. It's documentation, not constraints.

### The broad-test-command node
```markdown
## Rules
- make test
- npm run test
```
*Problem*: Runs entire test suite. Wastes 5+ minutes. Use targeted commands.

### The obvious-ownership node
```markdown
## Ownership
- routes.ts: routes
- config.ts: configuration
```
*Problem*: Adds zero information beyond what the filename says.

### The aspirational node
```markdown
## Contracts
- Code should be well-tested
- Follow clean code principles
```
*Problem*: Not verifiable, not specific to this codebase.

---

## Validation checklist

Before finalizing a node:

- [ ] Has Contracts section (mandatory)
- [ ] Contracts are specific and verifiable
- [ ] No broad test commands (make test, pytest, npm test)
- [ ] Every line passes: "Would an agent fixing a bug here need this?"
- [ ] Conditional sections only added when applicable
- [ ] No duplication with ancestor nodes
- [ ] Under 1500 tokens (under 1000 preferred)
