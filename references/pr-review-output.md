# PR Review Output Examples

Example outputs from `review_pr.sh` for reference.

## Low Risk Example

```markdown
# PR Review Summary

## Risk Assessment

**Score: 8 (Low)**

Contributing factors:
Files changed: +2
Contracts (2): +4
API patterns: +5

Recommendation: Standard review

---

## Review Checklist

### Relevant to this PR

- [ ] API responses must include X-Request-ID header (src/api/AGENTS.md)
      Changed: src/api/routes/users.ts

### Pitfalls in affected areas

- [ ] Rate limiter fails silently when Redis unavailable (src/api/AGENTS.md)
```

## High Risk AI-Generated Example

```markdown
# PR Review Summary

## Risk Assessment

**Score: 47 (High)**

Contributing factors:
Files changed: +3
Contracts (5): +10
Pitfalls (4): +12
Critical items (2): +10
Security patterns: +10
Data patterns: +10

Recommendation: Thorough review required

---

## Review Checklist

### Critical (always verify)

- [ ] ⚠️ Auth tokens must be validated before any database write (src/auth/AGENTS.md)
- [ ] CRITICAL: Never cache user permissions (src/api/AGENTS.md)

### Relevant to this PR

- [ ] All database writes require explicit transaction (src/db/AGENTS.md)
      Changed: src/db/repositories/user.ts

### Pitfalls in affected areas

- [ ] Migration rollback requires specific flag order (src/db/AGENTS.md)
- [ ] `config/legacy.json` looks unused but controls feature flags (CLAUDE.md)

---

## AI-Generated Code Checks

### Intent Drift Warnings

- Potential conflict: PR mentions JWT but src/auth/AGENTS.md says: use session tokens, NOT JWT

### Complexity Check

Potential over-engineering detected:

- New abstraction: src/utils/authHelper.ts
  Is this necessary or could existing patterns handle it?

- Excessive error handling: 5 new try/catch blocks
  Check if all error handling adds value

### Pitfall Proximity Alerts

AI modified code adjacent to known sharp edges:

- src/auth: Rate limiter fails silently when Redis unavailable
  Verify: Does new code handle this edge case?

- src/db: Migration scripts assume PostgreSQL 14+
  Verify: Does new code maintain compatibility?

---

## Detailed Context

### src/auth/AGENTS.md

**Covers:** 3 changed files

#### Contracts

- ⚠️ Auth tokens must be validated before any database write
- Session tokens expire after 1 hour
- Use bcrypt for password hashing (cost factor 12)

#### Pitfalls

- Rate limiter fails silently when Redis unavailable
- Token refresh window is 5 minutes before expiry

---

### src/db/AGENTS.md

**Covers:** 2 changed files

#### Contracts

- All writes require explicit transaction
- Migrations must be reversible
- CRITICAL: Never cache user permissions

#### Pitfalls

- Migration rollback requires `--lock-timeout=5000` flag
- Connection pool exhaustion at >100 concurrent queries
```

## CI Exit Codes

| Risk Level | Exit Code |
|------------|-----------|
| Low (0-15) | 0 |
| Medium (16-35) | 1 |
| High (36+) | 2 |
