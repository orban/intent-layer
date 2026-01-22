---
name: pr-review
description: >
  Review PRs against the Intent Layer. Use for reviewing AI-generated PRs
  or having AI review human PRs. Provides risk scoring, checklists, and
  contract verification.
argument-hint: "[BASE_REF] [HEAD_REF] [--pr NUMBER] [--ai-generated]"
---

# PR Review

Review a PR against the Intent Layer for contract compliance, pitfall awareness, and risk assessment.

## Quick Start

```bash
# Basic review
scripts/review_pr.sh main HEAD

# Review AI-generated PR
scripts/review_pr.sh main HEAD --ai-generated

# Review with GitHub PR context
scripts/review_pr.sh main HEAD --pr 123 --ai-generated
```

## Interactive Review Workflow

### Step 1: Run Initial Analysis

```bash
scripts/review_pr.sh main HEAD --ai-generated
```

Review the output:
1. **Risk Score** - Is this Low/Medium/High?
2. **Critical Items** - These MUST be verified
3. **AI Checks** - Any drift or over-engineering warnings?

### Step 2: Walk Through Critical Items

For each critical item in the checklist:
1. Read the contract/invariant
2. Find the relevant code in the diff
3. Verify the code respects the constraint
4. Mark checked: `- [x]` or flag concern

### Step 3: Check AI-Specific Warnings

If `--ai-generated` was used:

**Over-engineering flags:**
- New abstractions: Are they necessary?
- Excessive try/catch: Does error handling add value?
- New interfaces: Premature abstraction?

**Pitfall proximity:**
- For each alert, verify the AI handled the edge case
- If not, flag for fix before merge

**Intent drift:**
- If PR approach conflicts with documented architecture, escalate

### Step 4: Surface Findings

Use the agent-feedback-protocol format for any discoveries:

```markdown
### Intent Layer Feedback

| Type | Location | Finding |
|------|----------|---------|
| Missing pitfall | `src/api/AGENTS.md` | [description] |
| Stale contract | `CLAUDE.md` | [description] |
```

### Step 5: Generate Review Summary

Output a structured review comment:

```markdown
## PR Review Summary

**Risk: [Score] ([Level])**

### Verified
- [x] Auth tokens validated before DB write
- [x] Rate limiting uses Redis

### Concerns
- [ ] New abstraction in `utils/helper.ts` may be unnecessary

### Intent Layer Feedback
[Any findings to update nodes]
```

## CI Integration

```yaml
- name: PR Review Check
  run: |
    ./intent-layer/scripts/review_pr.sh origin/main HEAD --exit-code --ai-generated
  # Exit 0 = low risk, 1 = medium, 2 = high
```

## Output Modes

| Flag | Output |
|------|--------|
| `--summary` | Risk score only |
| `--checklist` | Score + checklist |
| `--full` | All layers (default) |

## When to Use

- **Before merging AI-generated PRs** - Verify contracts respected
- **AI reviewing human PRs** - Systematic contract checking
- **CI gate** - Block high-risk PRs for manual review

## Related

- `detect_changes.sh` - Foundation for affected node discovery
- `agent-feedback-protocol.md` - Format for surfacing findings
- `validate_node.sh` - Validate node updates after review
