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

## Integration Points

### During Task Completion
Before marking task complete, check if you encountered Intent Layer gaps.

### In PR/Code Review
Include Intent Layer feedback in PR description if findings emerged.

### Quarterly Maintenance
Use accumulated feedback as input to `intent-layer:maintain` skill.

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
