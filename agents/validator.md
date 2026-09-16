---
description: >
  Deep validation that an Intent Layer node accurately reflects its codebase.
  Use after creating/updating nodes or as part of PR review.
capabilities:
  - Compare documented contracts against actual code enforcement
  - Verify ownership mappings exist and are accurate
  - Check documented rules still apply
  - Flag undocumented constraints that appear frequently
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

#### Rules Validation

For each documented rule:
1. Check if the rule condition still exists in code
2. Look for recent fixes that might have resolved it
3. Search for new failure modes from recent commits

**Validation criteria:**
- PASS: Rule is current and relevant
- WARN: Rule may be outdated (related code changed)
- FAIL: Rule no longer applies (condition removed)

#### Boundaries Validation

For each documented boundary:
1. Search for import/dependency violations across covered files
2. Verify isolation rules are respected
3. Identify undocumented constraints

**Validation criteria:**
- PASS: Boundary respected consistently
- WARN: Boundary violated in some places
- FAIL: Boundary widely violated or no longer meaningful

#### Ownership Validation

For each documented file-to-responsibility mapping:
1. Verify file/function exists
2. Check if mapping is accurate (file still handles that responsibility)
3. Look for undocumented ownership gaps

**Validation criteria:**
- PASS: Mapping exists and is accurate
- WARN: File exists but responsibility shifted
- FAIL: File doesn't exist or is deprecated

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

#### Rules [STATUS]
| Rule | Status | Notes |
|------|--------|-------|
| "Auth token must be validated before..." | PASS | Guard at api/auth.ts:15 |
| "Never call X without locking" | WARN | Related code changed in commit abc123 |

#### Boundaries [STATUS]
...

#### Ownership [STATUS]
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
