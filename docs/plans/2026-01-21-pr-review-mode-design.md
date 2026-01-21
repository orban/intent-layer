# PR Review Mode Design

**Date:** 2026-01-21
**Status:** Approved

## Overview

PR review mode helps humans review AI-generated PRs and AI review human PRs using the Intent Layer as the shared source of truth.

## Use Cases

1. **Human reviewing AI-generated PRs** - Verify AI respects documented intent, contracts, patterns
2. **AI reviewing human PRs** - Check against Intent Layer contracts and pitfalls

## Components

### 1. review_pr.sh (Bash Script)

Location: `intent-layer/scripts/review_pr.sh`

**Usage:**
```bash
# Basic: git refs only
./review_pr.sh main HEAD

# With GitHub PR context
./review_pr.sh main HEAD --pr 123

# AI-generated code review (additional checks)
./review_pr.sh main HEAD --ai-generated

# Output options
./review_pr.sh main HEAD --summary      # Layer 1 only (risk score)
./review_pr.sh main HEAD --checklist    # Layers 1+2
./review_pr.sh main HEAD --full         # All layers (default)

# CI-friendly: exit code reflects risk level
./review_pr.sh main HEAD --exit-code
# Exit 0 = low, Exit 1 = medium, Exit 2 = high

# Output to file
./review_pr.sh main HEAD --output review.md
```

### 2. pr-review/SKILL.md (Interactive Skill)

Location: `intent-layer/pr-review/SKILL.md`

Guides agents through interactive review workflow:
1. Run review_pr.sh, present risk summary
2. Walk through checklist items
3. Surface findings using agent-feedback-protocol
4. Generate review summary for PR

## Output Layers (Progressive Disclosure)

### Layer 1: Risk Summary

```markdown
## Risk Summary

**Score: 42 (High)**

Contributing factors:
- 12 files changed (+2 pts)
- 5 contracts in affected nodes (+10 pts)
- 3 pitfalls in affected areas (+9 pts)
- 2 critical items (+10 pts)
- Security patterns detected (+10 pts)
- API patterns detected (+5 pts)

Recommendation: Thorough review required
```

### Layer 2: Review Checklist

```markdown
## Review Checklist

### Critical (always verify)
- [ ] ⚠️ Auth tokens must be validated before any database write (src/auth/AGENTS.md)
- [ ] CRITICAL: Never cache user permissions (src/api/AGENTS.md)

### Relevant to this PR
- [ ] Rate limiter requires Redis connection (src/api/AGENTS.md)
      ↳ Changed: src/api/middleware/rate-limit.ts

### Pitfalls in affected areas
- [ ] `config/legacy.json` looks unused but controls feature flags (CLAUDE.md)
```

### Layer 3: Detailed Context

Full excerpts from affected AGENTS.md files:
- Contracts & Invariants section
- Pitfalls section
- Anti-patterns section
- Entry Points (for reference)

## Risk Scoring System

### Quantitative Factors

| Factor | Points | Rationale |
|--------|--------|-----------|
| Files changed | 1 per 5 files | Scale/complexity indicator |
| Contracts in affected nodes | 2 per contract | More contracts = more to verify |
| Pitfalls in affected nodes | 3 per pitfall | Pitfalls are known sharp edges |
| Critical items (⚠️/CRITICAL:) | 5 per item | Explicitly marked high-risk |

### Semantic Signals

| Signal | Bonus | Patterns |
|--------|-------|----------|
| Security | +10 | auth, password, token, secret, permission, encrypt, credential |
| Data | +10 | migration, schema, DELETE, DROP, transaction, database |
| API | +5 | /api/, endpoint, route, breaking, deprecated |

### Score Thresholds

- **Low (0-15)**: Standard review
- **Medium (16-35)**: Careful review recommended
- **High (36+)**: Thorough review required

## Checklist Generation

### Sources Scanned

In affected AGENTS.md files:
- Contracts & Invariants section
- Pitfalls section
- Anti-patterns section

### Filtering Logic

```
For each item in affected nodes:
  if item starts with ⚠️ or CRITICAL:
    → ALWAYS include in checklist
  else if item contains keyword matching a changed file path
    → Include as "relevant"
  else
    → Omit (available in Layer 3 detail view)
```

## AI-Generated PR Mode

When `--ai-generated` flag is used, additional checks are performed:

### A. Intent Drift Detection

Compares PR title/description against Intent Layer:
- Flags when PR approach conflicts with documented architecture
- Checks ADRs and design decisions in affected nodes

```markdown
## Intent Alignment Check

PR Title: "Add user authentication"
PR Description: "Implements JWT-based auth with refresh tokens"

Relevant Intent Layer context:
- src/auth/AGENTS.md says: "Auth uses session tokens, NOT JWT (see ADR-003)"

⚠️ DRIFT DETECTED: PR approach may conflict with documented architecture
```

### B. Contract Verification Prompts

Generates specific YES/NO questions instead of just listing contracts:

```markdown
## Verification Questions (AI-generated code)

For each critical contract, answer YES/NO:

1. Auth tokens validated before DB write?
   → Check: src/api/routes/users.ts:45-67

2. Rate limiting uses Redis (not in-memory)?
   → Check: src/api/middleware/rate-limit.ts:12-30
```

### C. Over-Engineering Flags

Detects common AI over-engineering patterns:

```markdown
## Complexity Check

⚠️ Potential over-engineering detected:

- New abstraction layer added (src/utils/authHelper.ts)
  → Is this necessary or could existing patterns handle it?

- Try/catch wrapping simple operations (3 instances)
  → Check if error handling adds value or just noise

- New config options added (2 instances)
  → Are these needed now or speculative?
```

Patterns to flag:
- New files in `utils/`, `helpers/`, `common/`
- Excessive try/catch nesting
- New interfaces/types with single implementation
- Feature flags for non-experimental features

### D. Pattern Conformance Check

Compares generated code against documented patterns:

```markdown
## Pattern Conformance

Documented patterns in affected areas:

1. "API routes use controller pattern" (src/api/AGENTS.md)
   → Scan diff for route definitions, flag if inline handlers used

2. "Database access through repository layer" (src/db/AGENTS.md)
   → Flag direct SQL/ORM calls outside repository files

Findings:
- ✅ Routes use controller pattern
- ⚠️ Direct Prisma call in src/api/routes/users.ts:52 (expected: use UserRepository)
```

### E. Pitfall Proximity Warnings

More prominent alerts for AI-generated code:

```markdown
## ⚠️ Pitfall Alert

AI modified code adjacent to known sharp edges:

1. Rate limiter (src/api/middleware/rate-limit.ts)
   PITFALL: "Fails silently when Redis unavailable"
   → Verify: Does new code handle Redis disconnection?

2. Legacy config (touched package.json)
   PITFALL: "config/legacy.json looks unused but controls enterprise features"
   → Verify: No assumptions about config being unused
```

## File Structure

### New Files

```
intent-layer/
├── scripts/
│   └── review_pr.sh           # Main review script
├── pr-review/
│   └── SKILL.md               # Interactive review skill
└── references/
    └── pr-review-output.md    # Example output for reference
```

### Changes to Existing Files

- `intent-layer/SKILL.md` - Add pr-review to Resources table
- `CLAUDE.md` (root) - Add review_pr.sh to scripts table

## Dependencies

- `detect_changes.sh` (existing) - foundation for affected nodes
- `gh` CLI (optional) - for PR metadata when --pr flag used
- Standard coreutils (grep, awk, sed, etc.)

## Integration Points

### CI Usage

```yaml
- name: PR Review Check
  run: |
    ./intent-layer/scripts/review_pr.sh origin/main HEAD --exit-code --ai-generated
```

### Interactive Skill Workflow

1. Invoke skill: `/pr-review main HEAD --ai-generated`
2. Skill runs review_pr.sh internally
3. Presents risk summary, asks if reviewer wants to continue
4. Walks through checklist items interactively
5. Surfaces findings using agent-feedback-protocol format
6. Generates review comment for PR

## Non-Goals

- Automatic code fixes (review only)
- Custom risk patterns (use built-in set)
- Integration with specific CI systems (outputs standard markdown)
