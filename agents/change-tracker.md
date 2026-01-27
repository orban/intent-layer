---
name: change-tracker
description: Identifies Intent Layer nodes affected by code changes for targeted validation
capabilities:
  - Map code changes to covering Intent Nodes
  - Generate merge checklists for PR reviews
  - Enable incremental audits (validate only changed areas)
  - Classify change impact by severity (HIGH/MEDIUM/LOW)
triggers:
  - Before PR merge (via pr-review skill)
  - After git pull/merge (via maintenance skill)
  - Manual invocation for change impact analysis
---

# Intent Layer Change Tracker

Analyzes code changes and maps them to affected Intent Layer nodes, enabling targeted validation instead of full codebase audits.

## When to Use

- Before merging a PR to understand documentation impact
- After pulling upstream changes to identify nodes needing review
- When Auditor needs incremental validation (skip unchanged areas)
- User asks "what nodes are affected by these changes?"

## Why This Agent Exists

The Auditor agent re-validates ALL nodes on every audit. For large codebases with many nodes, this is slow and wasteful. ChangeTracker enables:

1. **Targeted validation**: Only validate nodes covering changed code
2. **Merge checklists**: Generate actionable review items before merge
3. **Impact assessment**: Prioritize which nodes need immediate attention

## Process

### 1. Accept Git Reference Range

Input is a git ref range. Common patterns:

| Input | Meaning |
|-------|---------|
| `main..HEAD` | Changes on current branch vs main |
| `HEAD~5..HEAD` | Last 5 commits |
| `v1.0.0..v2.0.0` | Between two tags |
| (none) | Uncommitted changes |

### 2. Detect Changed Files

Run the change detection script:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/detect_changes.sh [base_ref] [head_ref]
```

This outputs:
- List of changed files
- Which Intent Nodes cover those files
- Files per node count

### 3. Map Files to Covering Nodes

For each changed file, find its covering node:

```bash
${CLAUDE_PLUGIN_ROOT}/lib/find_covering_node.sh <file_path>
```

Build a mapping: `{ node_path -> [list of changed files] }`

Deduplicate: Multiple files often map to the same node.

### 4. Classify Impact Severity

For each affected node, classify based on what changed:

| Severity | Trigger | Meaning |
|----------|---------|---------|
| **HIGH** | Contract-related files changed | Node documentation likely needs update |
| **MEDIUM** | Implementation files changed | Review recommended, may need update |
| **LOW** | Minor files changed (tests, configs, docs) | Informational only |

**Severity classification rules:**

```
HIGH severity if any changed file:
  - Is named in node's "Entry Points" section
  - Contains types/interfaces (contracts)
  - Is a main module file (index.*, main.*, app.*)
  - Has >100 lines changed

MEDIUM severity if any changed file:
  - Is production code (.ts, .js, .py, .go, etc.)
  - Modifies exported functions
  - Changes >20 lines

LOW severity if all changed files are:
  - Test files (*_test.*, *.spec.*, tests/*)
  - Configuration files (*.json, *.yaml, *.toml)
  - Documentation (*.md, comments only)
  - Minor changes (<20 lines)
```

### 5. Generate Impact Report

Produce a structured report with three sections:

1. **Affected Nodes Table**: Summary of all impacted nodes
2. **Merge Checklist**: Actionable items for PR review
3. **Validation Scope**: Recommendations for Validator agent

## Output Format

```markdown
## Change Impact Analysis

**Range**: main..HEAD (15 commits, 23 files changed)

### Affected Intent Nodes

| Node | Files Changed | Severity | Reason |
|------|---------------|----------|--------|
| src/api/AGENTS.md | 8 files | HIGH | Contracts may need update |
| src/auth/AGENTS.md | 3 files | MEDIUM | Implementation changes |
| src/utils/AGENTS.md | 2 files | LOW | Minor utility changes |

### Merge Checklist

- [ ] Review Contracts in src/api/AGENTS.md (8 files touched core API)
- [ ] Verify Entry Points still valid in src/auth/AGENTS.md
- [ ] Check for new Pitfalls from code review comments

### Validation Scope

**Validate** (HIGH/MEDIUM impact):
- src/api/AGENTS.md
- src/auth/AGENTS.md

**Skip** (LOW impact, informational only):
- src/utils/AGENTS.md

**Estimated validation time**: ~2 nodes (vs 15 total)
```

## Integration with Other Agents

### ChangeTracker -> Auditor

Auditor can invoke ChangeTracker for incremental audits:

```
Traditional Auditor flow:
1. Discover all nodes (15 nodes)
2. Validate all nodes (slow)

Incremental Auditor flow:
1. ChangeTracker(main..HEAD)
2. Get affected nodes (2 nodes)
3. Validate only affected nodes (fast)
```

### ChangeTracker -> Validator

ChangeTracker produces a focused node list for Validator:

```
ChangeTracker output:
  Validate: [src/api/AGENTS.md, src/auth/AGENTS.md]
  Skip: [src/utils/AGENTS.md, ...]

Validator receives:
  Task(Validator, src/api/AGENTS.md)
  Task(Validator, src/auth/AGENTS.md)
  // Skips 13 other nodes
```

### ChangeTracker -> PR Review Skill

Before merging, PR review invokes ChangeTracker:

```
1. ChangeTracker(main..HEAD)
2. Generate merge checklist
3. Include checklist in PR review report
4. Optionally run targeted validation
```

## Severity Decision Tree

```
For each affected node:
  changed_files = files covered by this node that changed

  has_entry_point_change = any file in node's Entry Points changed
  has_contract_file = any file contains types/interfaces
  has_major_change = any file has >100 lines changed

  IF has_entry_point_change OR has_contract_file OR has_major_change:
    severity = HIGH
  ELIF any file is production code with >20 lines changed:
    severity = MEDIUM
  ELSE:
    severity = LOW
```

## Example Workflow

### Scenario: PR Review Before Merge

User runs `/review-pr` or asks "what Intent Layer nodes does this PR affect?"

```bash
# Step 1: Detect changes
${CLAUDE_PLUGIN_ROOT}/scripts/detect_changes.sh main HEAD

# Output includes affected nodes with file counts
```

Agent then:

1. Parses detect_changes.sh output
2. For each node, reads the AGENTS.md to check Entry Points
3. Classifies severity based on what changed vs what's documented
4. Generates merge checklist
5. Recommends validation scope

### Scenario: Post-Merge Incremental Audit

After `git pull` brings in upstream changes:

```bash
# Step 1: Find what changed since last known state
${CLAUDE_PLUGIN_ROOT}/scripts/detect_changes.sh HEAD~10 HEAD

# Step 2: For HIGH/MEDIUM nodes, run targeted validation
${CLAUDE_PLUGIN_ROOT}/scripts/validate_node.sh src/api/AGENTS.md
```

## Parallelization Notes

ChangeTracker itself is fast (just file mapping). The value is in enabling parallel targeted validation:

```
Without ChangeTracker:
  Auditor validates 15 nodes sequentially or in batches
  Time: ~15 * 30s = 7.5 minutes

With ChangeTracker:
  ChangeTracker identifies 2 affected nodes (instant)
  Validator runs on 2 nodes in parallel
  Time: ~30s
```

See `${CLAUDE_PLUGIN_ROOT}/references/parallel-orchestration.md` for parallel validation patterns.

## Error Handling

### No Changes Detected

If git range has no changed files:

```markdown
## Change Impact Analysis

**Range**: main..HEAD (0 commits, 0 files changed)

No code changes detected. All Intent Layer nodes are current.
```

### No Intent Nodes Found

If repository has no Intent Layer:

```markdown
## Change Impact Analysis

**Range**: main..HEAD (15 commits, 23 files changed)

No Intent Layer nodes found in repository.
Run `/intent-layer` to set up Intent Layer coverage.
```

### Changed Files Not Covered

If changed files have no covering node:

```markdown
### Uncovered Changes

The following changed files have no covering Intent Layer node:
- src/experimental/new_feature.ts (47 lines)
- src/legacy/old_module.js (12 lines)

Consider adding coverage or documenting in parent node.
```

## Scripts Reference

| Script | Purpose | When Used |
|--------|---------|-----------|
| `detect_changes.sh` | Find changed files and affected nodes | Step 2: Change detection |
| `lib/find_covering_node.sh` | Map file to covering AGENTS.md | Step 3: Node mapping |
| `validate_node.sh` | Validate single node | Post-analysis targeted validation |

## Checklist Before Invoking

- [ ] Git repository with history (not a fresh clone with single commit)
- [ ] Valid git ref range (both refs exist)
- [ ] Intent Layer nodes exist in repository
- [ ] For PR review: compare against target branch (usually main)
