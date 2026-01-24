---
description: >
  Deep validation that an Intent Layer node accurately reflects its codebase.
  Use after creating/updating nodes or as part of PR review.
capabilities:
  - Compare documented contracts against actual code enforcement
  - Verify entry points exist and are accurate
  - Check documented patterns are actually followed
  - Flag undocumented patterns that appear frequently
  - Generate validation reports with PASS/WARN/FAIL status
---

# Intent Layer Validator

Validates that AGENTS.md/CLAUDE.md nodes accurately reflect their covered codebase.

## When to Use

- After creating or updating an Intent Layer node
- As part of PR review when changes touch covered areas
- When user asks to "validate intent layer" or "check AGENTS.md accuracy"
- Before marking a node as production-ready

## Validation Process

### 1. Load the Node

Read the AGENTS.md file and parse its sections:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/validate_node.sh <path-to-agents-md>
```

The script provides structural validation. This agent does deep semantic validation.

### 2. Validate Each Section

#### Contracts Validation

For each documented contract:
1. Search for enforcement in code (guards, assertions, type checks)
2. Look for violations that would indicate stale documentation
3. Check if contract scope matches reality

**Validation criteria:**
- PASS: Contract enforced in code, no violations found
- WARN: Contract mentioned but enforcement unclear
- FAIL: Contract violated in code, or no enforcement exists

#### Entry Points Validation

For each documented entry point:
1. Verify file/function exists
2. Check if it's actually used as an entry point (imported/called)
3. Look for undocumented entry points

**Validation criteria:**
- PASS: Entry point exists and is actively used
- WARN: Entry point exists but usage unclear
- FAIL: Entry point doesn't exist or is deprecated

#### Pitfalls Validation

For each documented pitfall:
1. Check if the pitfall condition still exists in code
2. Look for recent fixes that might have resolved it
3. Search for new pitfalls from recent commits

**Validation criteria:**
- PASS: Pitfall is current and relevant
- WARN: Pitfall may be outdated (related code changed)
- FAIL: Pitfall no longer applies (condition removed)

#### Patterns Validation

For each documented pattern:
1. Search for pattern usage across covered files
2. Count adherence vs. violations
3. Identify undocumented patterns with high usage

**Validation criteria:**
- PASS: Pattern followed consistently (>80% adherence)
- WARN: Pattern followed inconsistently (50-80%)
- FAIL: Pattern not followed (<50%) or contradicted

### 3. Generate Validation Report

```markdown
## Validation Report: <path-to-node>

### Summary
- **Overall Status**: PASS | WARN | FAIL
- **Sections Validated**: N
- **Issues Found**: X warnings, Y failures

### Section Results

#### Contracts [STATUS]
| Contract | Status | Evidence |
|----------|--------|----------|
| "Auth required for /api/*" | PASS | Middleware at api/auth.ts:15 |
| "Rate limit 100/min" | WARN | Config exists but no enforcement found |

#### Entry Points [STATUS]
| Entry Point | Status | Notes |
|-------------|--------|-------|
| src/api/index.ts | PASS | Main API router |
| src/utils/deprecated.ts | FAIL | File deleted in commit abc123 |

#### Pitfalls [STATUS]
...

#### Patterns [STATUS]
...

### Recommendations
1. [Specific actions to resolve failures]
2. [Suggestions for warnings]
3. [Undocumented items to consider adding]
```

## Integration Points

- **Explorer** → creates draft → **Validator** verifies
- **Auditor** → spawns **Validator** for each node
- **PostToolUse hook** → flags files → **Validator** checks affected nodes

## Validation Thresholds

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| PASS | Node accurately reflects code | None |
| WARN | Minor discrepancies or uncertainty | Review recommended |
| FAIL | Significant inaccuracy detected | Update required |

Overall status is the worst status of any section.
