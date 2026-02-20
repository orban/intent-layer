---
name: intent-layer:query
description: >
  Query the Intent Layer to answer questions about the codebase.
  Use when asking "what owns X?", "where should I put Y?", "what constraints apply to Z?",
  or navigating an unfamiliar codebase using its AGENTS.md hierarchy.
argument-hint: "[/path/to/project] [query]"
---

# Intent Layer Query

Query an existing Intent Layer to answer architectural and navigation questions.

## Prerequisites

- Project must have Intent Layer state = `complete`
- Run `intent-layer` skill first if state is `none` or `partial`

## Quick Start

```bash
# Check state first
${CLAUDE_PLUGIN_ROOT}/scripts/detect_state.sh /path/to/project

# View hierarchy
${CLAUDE_PLUGIN_ROOT}/scripts/show_hierarchy.sh /path/to/project

# Check health
${CLAUDE_PLUGIN_ROOT}/scripts/show_status.sh /path/to/project
```

---

## Query Types

### 1. Ownership Queries

**"What owns X?"** - Find responsible component for a concept.

**Process:**
1. Search all Intent Nodes for the concept
2. Return the most specific node that claims ownership
3. Include parent context for full picture

**Example:**
```
Q: "What owns authentication?"

Search: grep -r "authentication\|auth" in CLAUDE.md/AGENTS.md files
Result: src/auth/AGENTS.md owns authentication
Parent: CLAUDE.md references auth as critical subsystem
```

**Output format:**
```markdown
## Ownership: [concept]

**Primary owner:** `path/to/AGENTS.md`
> [TL;DR from that node]

**Parent context:** `CLAUDE.md`
> [Relevant excerpt about this area]

**Contracts:**
- [Any constraints from owner or ancestors]
```

---

### 2. Placement Queries

**"Where should I put X?"** - Find correct location for new code.

**Process:**
1. Identify the responsibility of X
2. Find nodes with matching or adjacent responsibilities
3. Check for explicit "out of scope" declarations
4. Recommend placement with rationale

**Example:**
```
Q: "Where should I put a new payment processor?"

Analysis:
- payments/ exists → check src/payments/AGENTS.md
- If AGENTS.md says "owns all payment logic" → put there
- If AGENTS.md says "only Stripe" → may need new sibling
```

**Output format:**
```markdown
## Placement: [new thing]

**Recommended:** `path/to/directory/`
**Reason:** [Why this location based on Intent Layer]

**Relevant contracts:**
- [Constraints that apply to this location]

**Alternatives considered:**
- `other/path/` - rejected because [reason from Intent Layer]
```

---

### 3. Constraint Queries

**"What constraints apply to X?"** - Gather all rules for an area.

**Process:**
1. Find the most specific node for X
2. Walk up to root, collecting constraints
3. Merge contracts from all ancestors (child overrides parent)
4. Return unified constraint set

**Example:**
```
Q: "What constraints apply to the API layer?"

Walk: src/api/AGENTS.md → CLAUDE.md
Collect:
- From src/api/AGENTS.md: "All endpoints must validate auth token"
- From CLAUDE.md: "Never log PII", "Use structured logging"
```

**Output format:**
```markdown
## Constraints: [area]

### From `path/to/specific/AGENTS.md`
- [Local constraints]

### Inherited from `CLAUDE.md`
- [Global constraints that apply]

### Effective rules (merged)
1. [Most important constraint]
2. [Second constraint]
...
```

---

### 4. Entry Point Queries

**"How do I [task]?"** - Find starting point for common tasks.

**Process:**
1. Search Entry Points sections across all nodes
2. Match task description to documented entry points
3. Return the most specific match with context

**Example:**
```
Q: "How do I add a new API endpoint?"

Search Entry Points for: "API", "endpoint", "route"
Match: src/api/AGENTS.md → Entry Points → "Add endpoint: start at routes/"
```

**Output format:**
```markdown
## Entry Point: [task]

**Start here:** `path/to/file.ts`
**From:** `path/to/AGENTS.md`

**Steps:**
1. [Step from Entry Points section]
2. [Additional context if available]

**Watch out for:**
- [Relevant pitfalls from same node]
```

---

### 5. Pitfall Queries

**"What can go wrong with X?"** - Gather warnings for an area.

**Process:**
1. Find nodes covering X
2. Collect all Pitfalls sections
3. Include parent pitfalls that apply
4. Return consolidated warnings

**Output format:**
```markdown
## Pitfalls: [area]

### Critical (from nearest node)
- [Pitfall 1]
- [Pitfall 2]

### Inherited (from ancestors)
- [Global pitfall that applies]

### Related anti-patterns
- [Things to avoid]
```

---

### 6. Architecture Queries

**"Why is X designed this way?"** - Find rationale for decisions.

**Process:**
1. Search Architecture Decisions sections
2. Look for ADR links
3. Check Related Context for external docs

**Output format:**
```markdown
## Architecture: [topic]

**Decision:** [What was decided]
**Rationale:** [Why, from Architecture Decisions section]
**Source:** `path/to/AGENTS.md` or linked ADR

**Related:**
- [Links to ADRs or design docs]
```

---

## Interactive Query Workflow

For complex queries, use this interactive process:

### Step 1: Understand the Question

Classify the query:
- Ownership → "What owns..."
- Placement → "Where should..."
- Constraints → "What rules..."
- Entry Point → "How do I..."
- Pitfalls → "What can go wrong..."
- Architecture → "Why is..."

### Step 2: Gather Context

```bash
# View full hierarchy
${CLAUDE_PLUGIN_ROOT}/scripts/show_hierarchy.sh /path/to/project

# Search for concept in Intent Nodes
grep -r "concept" --include="CLAUDE.md" --include="AGENTS.md" /path/to/project
```

### Step 3: Walk the Hierarchy

For the relevant node:
1. Read the specific node
2. Read each ancestor up to root
3. Collect relevant sections

### Step 4: Synthesize Answer

Combine findings into the appropriate output format (see Query Types above).

### Step 5: Cite Sources

Always include:
- Which nodes provided the answer
- Line numbers for specific claims
- Confidence level (explicit vs inferred)

---

## Query Confidence Levels

| Level | Meaning |
|-------|---------|
| **Explicit** | Directly stated in Intent Node |
| **Inferred** | Derived from multiple nodes |
| **Uncertain** | Not documented, using code analysis |

Always state confidence:
```markdown
**Confidence:** Explicit (from src/auth/AGENTS.md:15)
```

or

```markdown
**Confidence:** Inferred (no direct documentation, based on code structure)
**Recommendation:** Add to Intent Layer via maintenance skill
```

---

## When Query Fails

If the Intent Layer doesn't answer the question:

### 1. Document the Gap

```markdown
### Intent Layer Feedback

| Type | Location | Finding |
|------|----------|---------|
| Missing ownership | `CLAUDE.md` | No documented owner for [concept] |
```

### 2. Answer from Code

Fall back to code analysis, but flag uncertainty:

```markdown
## Answer (from code analysis)

**Confidence:** Uncertain - not documented in Intent Layer

[Answer based on code reading]

**Recommendation:** Document this in [suggested node]
```

### 3. Trigger Maintenance

If multiple gaps found, suggest running `intent-layer:maintain` skill.

---

## Parallel Queries (Large Intent Layers)

For Intent Layers with 5+ nodes or complex multi-faceted queries, use parallel subagents.

### When to Use Parallel Queries

| Scenario | Approach |
|----------|----------|
| Single concept, small Intent Layer | Sequential search |
| Single concept, large Intent Layer (5+ nodes) | Parallel node search |
| Multi-faceted query (ownership + constraints + pitfalls) | Parallel aspect search |
| Cross-cutting concern investigation | Parallel subsystem search |

### Parallel Node Search

Search all nodes simultaneously for a concept:

```
Task 1 (Explore): "Search CLAUDE.md for references to [concept].
                   Return: any mentions, ownership claims, constraints, pitfalls"

Task 2 (Explore): "Search src/api/AGENTS.md for references to [concept].
                   Return: any mentions, ownership claims, constraints, pitfalls"

Task 3 (Explore): "Search src/core/AGENTS.md for references to [concept].
                   Return: any mentions, ownership claims, constraints, pitfalls"
```

**Synthesis**: Combine results, identify primary owner (most specific claim), collect all constraints.

### Parallel Aspect Search

For complex queries needing multiple perspectives:

```
Q: "What do I need to know to add a new payment provider?"

Task 1 (Explore): "Search Intent Layer for ownership of payments.
                   Who owns payment logic? What's in scope/out of scope?"

Task 2 (Explore): "Search Intent Layer for payment-related contracts.
                   What invariants apply? What patterns are required?"

Task 3 (Explore): "Search Intent Layer for payment-related pitfalls.
                   What surprises exist? What has broken before?"

Task 4 (Explore): "Search Intent Layer for payment entry points.
                   How do I add new payment functionality?"
```

**Synthesis**: Combine into comprehensive answer covering ownership, constraints, warnings, and starting point.

### Parallel Cross-Cutting Search

For concepts that span multiple subsystems:

```
Q: "How is authentication handled across the system?"

Task 1 (Explore): "Search src/api/AGENTS.md for auth mentions.
                   How does API layer handle auth?"

Task 2 (Explore): "Search src/core/AGENTS.md for auth mentions.
                   How does core layer handle auth?"

Task 3 (Explore): "Search src/db/AGENTS.md for auth mentions.
                   How does data layer handle auth?"
```

**Synthesis**: Map auth flow across subsystems, identify gaps in documentation.

### Parallel Query Benefits

| Query Type | Sequential | Parallel |
|------------|------------|----------|
| Concept in 8 nodes | ~16 reads | ~3 reads (parallel) |
| Multi-aspect query | ~12 reads | ~4 reads (parallel) |
| Cross-cutting search | ~10 reads | ~3 reads (parallel) |

### Example: Parallel Constraint Query

**Query**: "What constraints apply to the checkout flow?"

**Parallel execution**:
```
Task 1: "Find all constraints in src/checkout/AGENTS.md"
Task 2: "Find all constraints in src/payments/AGENTS.md"
Task 3: "Find all global constraints in CLAUDE.md that mention checkout, payment, or transaction"
```

**Synthesis output**:
```markdown
## Constraints: checkout flow

### From `src/checkout/AGENTS.md`
- Cart must be validated before payment initiation
- Inventory reserved for 15 minutes during checkout

### From `src/payments/AGENTS.md`
- All payment calls must be idempotent
- Failed payments must not leave partial state

### Inherited from `CLAUDE.md`
- All financial operations must be logged
- PII never logged in plain text

### Effective rules (merged)
1. Validate cart → reserve inventory → initiate payment (order matters)
2. Payment calls must be idempotent
3. Log all operations, redact PII
4. 15-minute timeout on reservations
```

---

## Common Query Patterns

| Question Pattern | Query Type | Key Sections to Check |
|-----------------|------------|----------------------|
| "What handles X?" | Ownership | TL;DR, Subsystem Boundaries |
| "Where does X live?" | Ownership | Subsystem Boundaries, Downlinks |
| "Where should I add X?" | Placement | Ownership + Out of Scope |
| "Can I do X here?" | Constraints | Contracts, Anti-patterns |
| "What rules apply to X?" | Constraints | Contracts (all ancestors) |
| "How do I X?" | Entry Point | Entry Points section |
| "What's dangerous about X?" | Pitfalls | Pitfalls, Anti-patterns |
| "Why X instead of Y?" | Architecture | Architecture Decisions |

---

## Scripts Reference

This skill uses scripts from `intent-layer`:

| Script | Query Use |
|--------|-----------|
| `show_hierarchy.sh` | Visualize full Intent Layer structure |
| `show_status.sh` | Check health before querying |
| `detect_state.sh` | Verify Intent Layer exists |

All paths: `${CLAUDE_PLUGIN_ROOT}/scripts/`

---

## Examples

### Example 1: Ownership Query

**User:** "What owns user sessions?"

**Process:**
1. `grep -r "session" --include="*.md"` in Intent Nodes
2. Found in `src/auth/AGENTS.md`: "Owns: authentication, sessions, tokens"
3. Parent `CLAUDE.md` confirms: "Auth subsystem handles all identity"

**Answer:**
```markdown
## Ownership: user sessions

**Primary owner:** `src/auth/AGENTS.md`
> Owns authentication, session management, and token lifecycle.

**Contracts:**
- Sessions must expire after 24h inactivity
- Session tokens never logged

**Confidence:** Explicit (src/auth/AGENTS.md:23)
```

### Example 2: Placement Query

**User:** "Where should I add rate limiting?"

**Process:**
1. Search for "rate limit" - not found
2. Search for "middleware", "request handling"
3. Found `src/api/AGENTS.md` owns "request pipeline"
4. Check if rate limiting is out of scope - no
5. Check constraints - "middleware must be stateless"

**Answer:**
```markdown
## Placement: rate limiting

**Recommended:** `src/api/middleware/`
**Reason:** API layer owns request pipeline, rate limiting is request-level concern

**Constraints from Intent Layer:**
- Middleware must be stateless (use Redis for counters)
- All middleware must log to structured logger

**Confidence:** Inferred (no explicit mention, derived from ownership)
**Recommendation:** Add rate limiting to src/api/AGENTS.md Entry Points
```
