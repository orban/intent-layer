# Agent Feedback Protocol

How agents surface missing context during normal work, creating a continuous improvement loop.

## The Flywheel

```
┌─────────────────────────────────────────────────────────┐
│  Agent works on task using Intent Layer                 │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Agent encounters gap (missing pitfall, stale contract) │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Agent surfaces finding in structured format            │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Human reviews: Accept → Reject → Defer                 │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Intent Layer updated → Future agents start better      │
└─────────────────────────────────────────────────────────┘
```

## When to Surface Findings

During normal work, flag when you encounter:

| Trigger | What to Surface |
|---------|-----------------|
| Code contradicts Intent Node | Flag for human review |
| Undocumented pattern discovered | Propose addition to Patterns |
| Sharp edge caught you off guard | Propose addition to Pitfalls |
| Contract seems violated or outdated | Flag stale contract |
| Code looks dead but might not be | Flag as "suspected dead code" |
| Missing entry point for common task | Propose addition to Entry Points |
| Couldn't find file/function quickly | Propose addition to Code Map |
| External service failed unexpectedly | Propose addition to External Dependencies |
| Couldn't trace request flow | Propose addition to Data Flow |
| Didn't understand WHY something exists | Flag missing Design Rationale |
| Proposed change rejected due to design philosophy | Flag Design Rationale violation |

## Surfacing Format

At end of task (or when significant findings accumulate):

```markdown
### Intent Layer Feedback

| Type | Location | Finding |
|------|----------|---------|
| Missing pitfall | `src/api/AGENTS.md` | Rate limiter silently drops requests when Redis unavailable |
| Stale contract | `CLAUDE.md` | API v2 endpoints now require `X-Trace-ID` header |
| Suspected dead | `src/legacy/old_auth.py` | No references found - verify with team |
| Missing pattern | `src/db/AGENTS.md` | Migration rollback requires specific flag order |
| Missing code map | `src/auth/AGENTS.md` | Couldn't find session validation logic - was in `utils/session.ts` |
| Missing ext dep | `src/api/AGENTS.md` | Redis failure mode not documented - causes silent rate limit bypass |
| Missing data flow | `src/payments/AGENTS.md` | Couldn't trace refund flow for debugging |
| Missing rationale | `src/core/AGENTS.md` | Why does `sansio/` exist? Had to dig through git history |
| Rationale violation | `src/core/AGENTS.md` | Proposed global state, rejected because of thread-safety constraint |
```

## Finding Types

### Missing Pitfall
Something surprising that would catch future agents/engineers off guard.

**Template**: "[Component] [unexpected behavior] when [condition]"

**Examples**:
- "Rate limiter silently drops requests when Redis unavailable"
- "`config/legacy.json` looks unused but controls enterprise feature flags"
- "Running `make clean` deletes cached auth tokens"

### Stale Contract
A documented invariant that no longer holds, or a new invariant that should be documented.

**Template**: "[What changed] - [old state] → [new state]"

**Examples**:
- "API v2 endpoints now require `X-Trace-ID` header (added in v2.3)"
- "Auth tokens now expire after 1 hour (was 24 hours)"
- "Database writes now require explicit transaction (was auto-commit)"

### Suspected Dead Code
Code that appears unused but deletion might break something non-obvious.

**Template**: "[Path] - [evidence] - verify before deleting"

**Examples**:
- "`src/legacy/converter.py` - no imports found - verify with team"
- "`scripts/migrate_v1.sh` - references v1 schema - may be needed for rollback"

### Missing Pattern
A common task that lacks documentation on how to do it correctly.

**Template**: "To [task], need to [non-obvious steps]"

**Examples**:
- "To add a new API endpoint, must also update rate limit config"
- "To run migrations, must use `--lock-timeout=5000` flag in production"

### Missing Entry Point
A common task that should be in the Entry Points table but isn't.

**Template**: "[Task description] → [starting file/location]"

### Missing Code Map Entry
Couldn't find something quickly - had to search/grep to locate.

**Template**: "Looking for [X] → was in [Y] (not obvious)"

**Examples**:
- "Session validation logic → was in `utils/session.ts`, not `auth/`"
- "Rate limit config → was in `config/limits.yaml`, not `api/config.ts`"

### Missing External Dependency
External service failed and the failure mode wasn't documented.

**Template**: "[Service] failure mode: [what happened]"

**Examples**:
- "Redis unavailable → rate limiter silently bypassed (should fail closed)"
- "S3 timeout → file upload hung indefinitely (no timeout configured)"

### Missing Data Flow
Couldn't trace how data moves through the system for debugging.

**Template**: "Couldn't trace [operation] flow for debugging"

**Examples**:
- "Couldn't trace refund flow - spans 4 services, no diagram"
- "Error propagation unclear - didn't know where to add logging"

### Missing Design Rationale
Didn't understand WHY something was designed a certain way.

**Template**: "Why does [X] exist/work this way? Had to [how discovered]"

**Examples**:
- "Why does `sansio/` exist? Had to dig through git history to understand async separation"
- "Why LocalProxy instead of direct context? Not documented, figured out from Werkzeug docs"

### Design Rationale Violation
Proposed a change that was rejected because it violated the design philosophy.

**Template**: "Proposed [change], rejected because [design constraint violated]"

**Examples**:
- "Proposed global state, rejected because of thread-safety constraint"
- "Proposed auto-discovery, rejected because 'explicit is better than implicit'"
- "Proposed direct DB access, rejected because of layer isolation"

**Note**: This is the highest-value feedback type. It reveals strategic knowledge that prevents repeated mistakes. Always capture the constraint that was violated.

## Human Review Workflow

When agent surfaces findings, human should:

### Accept
Finding is accurate → Update the Intent Node immediately

### Reject
Finding is incorrect → Note why (helps calibrate future agents):
- "That code path is actually used by batch jobs"
- "The contract change was intentional and documented in ADR-015"

### Defer
Finding needs investigation → Add to maintenance backlog:
- Suspected dead code needs team verification
- Contract change needs broader review
- Pattern needs validation across more cases

## Automatic Surfacing Trigger

Agents should surface findings at these checkpoints:

### End of Task (Required)
Before marking any task complete:
1. **Pause and reflect**: "Did I encounter any Intent Layer gaps?"
2. **Check each category**:
   - Navigation struggles → Code Map
   - Surprising behaviors → Pitfalls
   - Violated assumptions → Contracts
   - Failed services → External Dependencies
   - Design confusion → Design Rationale
3. **Surface if any**: Use the structured format above

### After Debugging (Required)
When you spend significant time debugging:
- Document what was hard to trace → Data Flow
- Document what you didn't know → Design Rationale or Pitfalls
- Document the fix → Patterns or Pre-flight Checks

### After Rejection (Required)
When your proposed change is rejected:
- Document the constraint that was violated → Design Rationale
- This is the highest-value feedback

## Integration Points

### During Task Completion
Before marking task complete, check if you encountered Intent Layer gaps.

### In PR/Code Review
Include Intent Layer feedback in PR description if findings emerged.

### Quarterly Maintenance
Use accumulated feedback as input to `intent-layer-maintenance` skill.

## Metrics Tracking

Track these metrics to measure Intent Layer effectiveness:

### Per-Project Metrics

Store in `.intent-layer/metrics.json`:

```json
{
  "findings": {
    "total_surfaced": 45,
    "accepted": 32,
    "rejected": 8,
    "deferred": 5
  },
  "by_type": {
    "missing_pitfall": 15,
    "missing_code_map": 10,
    "missing_rationale": 7,
    "rationale_violation": 5,
    "stale_contract": 4,
    "missing_pattern": 4
  },
  "avg_resolution_days": 2.3,
  "last_audit": "2026-01-15"
}
```

### Key Questions Metrics Answer

| Question | Metric |
|----------|--------|
| Is Intent Layer being used? | Findings surfaced per month |
| Are we acting on feedback? | Accepted / Total ratio |
| What's most commonly missing? | By-type breakdown |
| Are we keeping up? | Avg resolution days |
| When did we last review? | Last audit date |

### Reviewing Metrics

During quarterly maintenance:
1. Review by-type breakdown → Focus capture on gaps
2. Check accepted/rejected ratio → Calibrate agent surfacing
3. If resolution time growing → Process backlog or simplify workflow

## Example Workflow

**Agent working on auth feature:**

1. Reads `src/auth/AGENTS.md` - follows documented patterns
2. Discovers rate limiter has undocumented Redis dependency
3. Gets caught by silent failure mode
4. Completes task successfully (after debugging)
5. Surfaces finding:

```markdown
### Intent Layer Feedback

| Type | Location | Finding |
|------|----------|---------|
| Missing pitfall | `src/auth/AGENTS.md` | Rate limiter fails silently when Redis unavailable - requests pass through unthrottled |
```

6. Human accepts → Updates `src/auth/AGENTS.md` Pitfalls section
7. Future agents don't repeat the discovery process
