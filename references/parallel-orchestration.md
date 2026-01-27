# Parallel Agent Orchestration

How to run Intent Layer agents in parallel for large codebases.

> Parallelization trades simplicity for speed. Only parallelize when the codebase is large enough to justify the complexity.

## Quick Reference

| Scenario | Parallelize? | Reason |
|----------|--------------|--------|
| >3 nodes to validate | Yes | Independent validation tasks |
| >5 directories to explore | Yes | Independent analysis tasks |
| >100k token codebase audit | Yes | Reduces total wall-clock time |
| Explorer → Validator | No | Sequential dependency |
| <50k token codebase | No | Overhead exceeds benefit |
| Results inform next step | No | Sequential dependency |

## Agent Capabilities Summary

| Agent | Input | Output | Parallelizable |
|-------|-------|--------|----------------|
| **Explorer** | Directory path | Proposed AGENTS.md draft | Yes (across directories) |
| **Validator** | AGENTS.md path | PASS/WARN/FAIL report | Yes (across nodes) |
| **Auditor** | Repository root | Aggregated health report | Spawns parallel Validators |

## When to Parallelize

### Multiple Independent Validations

When you have 3+ nodes that need validation and no dependencies between them:

```
Trigger: User asks "validate all nodes" or "check intent layer health"
Condition: >3 AGENTS.md files exist

Execute in parallel:
- Validator(src/api/AGENTS.md)
- Validator(src/auth/AGENTS.md)
- Validator(src/db/AGENTS.md)
```

### Multiple Independent Explorations

When analyzing a large codebase with 5+ candidate directories:

```
Trigger: User asks to "add intent layer" to large codebase
Condition: detect_state.sh shows >5 candidate directories

Execute in parallel:
- Explorer(src/api/)
- Explorer(src/auth/)
- Explorer(src/models/)
- Explorer(src/workers/)
```

### Large Codebase Audit

When total codebase exceeds 100k tokens:

```
Trigger: User asks for "quarterly audit" or "check for drift"
Condition: Codebase >100k tokens, >5 nodes exist

Auditor workflow:
1. Discover all nodes (show_hierarchy.sh)
2. Run detect_staleness.sh for quick triage
3. Batch parallel Validators for stale nodes
```

## When NOT to Parallelize

### Sequential Dependencies

Explorer output must complete before Validator can verify:

```
WRONG:
  Explorer(src/api/) + Validator(src/api/AGENTS.md)  # AGENTS.md doesn't exist yet

RIGHT:
  Explorer(src/api/)
  → Wait for completion
  → Validator(src/api/AGENTS.md)
```

### Small Codebases

Orchestration overhead exceeds parallelization benefit:

```
<50k tokens total → Run sequentially
<3 nodes → Run sequentially
<5 directories → Run sequentially
```

### Results Inform Next Step

When analysis from one task changes what the next task should do:

```
WRONG:
  Explorer(src/) in parallel with Explorer(src/api/)
  # src/api/ might be covered by src/ node

RIGHT:
  Explorer(src/)
  → Review: does src/ node cover api/?
  → If no: Explorer(src/api/)
```

## How to Invoke Parallel Agents

For skills and Claude Code workflows, invoke the Task tool multiple times in a single response:

### Parallel Validation Example

```markdown
Validating multiple nodes concurrently. Invoking three parallel tasks:

Task(agent: "Validator", input: "src/api/AGENTS.md")
Task(agent: "Validator", input: "src/auth/AGENTS.md")
Task(agent: "Validator", input: "src/db/AGENTS.md")

All three run concurrently. Results will be aggregated below.
```

### Parallel Exploration Example

```markdown
Analyzing multiple directories concurrently. Invoking four parallel tasks:

Task(agent: "Explorer", input: "src/api/")
Task(agent: "Explorer", input: "src/auth/")
Task(agent: "Explorer", input: "src/models/")
Task(agent: "Explorer", input: "src/workers/")

Will collect proposals and identify cross-cutting concerns for LCA placement.
```

## Result Aggregation Patterns

### Validation Results

Merge individual reports into unified summary:

```markdown
## Aggregated Validation Report

### Summary
| Node | Status | Issues |
|------|--------|--------|
| src/api/AGENTS.md | PASS | 0 |
| src/auth/AGENTS.md | WARN | 2 warnings |
| src/db/AGENTS.md | FAIL | 1 failure |

**Overall Status**: FAIL (worst of all nodes)
**Total Issues**: 2 warnings, 1 failure

### Detailed Results

#### src/api/AGENTS.md - PASS
[Full report from Validator]

#### src/auth/AGENTS.md - WARN
[Full report from Validator]

#### src/db/AGENTS.md - FAIL
[Full report from Validator]
```

### Exploration Results

Merge proposals, deduplicate cross-cutting concerns:

```markdown
## Aggregated Exploration Results

### Proposed Nodes
| Directory | Confidence | Tokens | Action |
|-----------|------------|--------|--------|
| src/api/ | HIGH | ~2.5k | Create node |
| src/auth/ | HIGH | ~1.8k | Create node |
| src/models/ | MEDIUM | ~3.2k | Create node |
| src/workers/ | LOW | ~800 | Merge into parent |

### Cross-Cutting Concerns Identified
Found in 3+ proposals → move to LCA:

| Concern | Found In | LCA Placement |
|---------|----------|---------------|
| "All DB calls via repository" | api, auth, models | src/AGENTS.md |
| "JWT auth required" | api, auth, workers | Root CLAUDE.md |

### Recommendations
1. Create nodes for api/, auth/, models/
2. Merge workers/ content into parent node
3. Add cross-cutting concerns to appropriate LCA
```

### Audit Results

Combine staleness reports, unify coverage gaps:

```markdown
## Aggregated Audit Report

### Health Summary
| Status | Count | Nodes |
|--------|-------|-------|
| Healthy | 5 | [list] |
| Needs Attention | 3 | [list] |
| Critical | 1 | src/db/AGENTS.md |

### Prioritized Issues

#### P0 - Critical (Contract Failures)
- src/db/AGENTS.md: Migration contract outdated

#### P1 - High (Entry Point Failures)
- src/api/AGENTS.md: Deleted route still documented

#### P2 - Medium (Staleness)
- src/auth/AGENTS.md: 15 commits since last update

### Coverage Gaps
Directories with code but no coverage:
- src/legacy/ (12k tokens) - recommend: create node
- src/scripts/ (3k tokens) - recommend: cover in parent
```

## Error Handling

### Partial Failure Recovery

If one parallel agent fails, continue others and report partial results:

```markdown
## Validation Results (Partial)

**Note**: 1 of 4 validations failed. Showing available results.

### Successful Validations
| Node | Status |
|------|--------|
| src/api/AGENTS.md | PASS |
| src/auth/AGENTS.md | WARN |
| src/db/AGENTS.md | PASS |

### Failed Validations
| Node | Error |
|------|-------|
| src/workers/AGENTS.md | Timeout after 30s |

### Recommended Action
- Review results above
- Retry failed validation: `validate_node.sh src/workers/AGENTS.md`
```

### Retry Strategy

Retry failed agents once before giving up:

```
First attempt: Parallel batch of 4 Validators
Result: 3 succeed, 1 fails (timeout)

Retry: Single Validator for failed node
Result: Success → Add to aggregated report
     OR Failure → Report as partial result
```

### Timeout Handling

Set reasonable timeouts based on operation type:

| Operation | Timeout | Rationale |
|-----------|---------|-----------|
| Validator | 30s | Deep code analysis |
| Explorer | 60s | Structure analysis + git mining |
| Auditor (per node) | 30s | Same as Validator |
| Full audit | 10min | Many nodes |

## Concrete Examples

### Example 1: Parallel Audit (Auditor spawning Validators)

Scenario: Quarterly maintenance audit of 8 nodes.

```
Step 1: Discovery
$ ${CLAUDE_PLUGIN_ROOT}/scripts/show_hierarchy.sh
→ Found 8 AGENTS.md files

Step 2: Staleness Check
$ ${CLAUDE_PLUGIN_ROOT}/scripts/detect_staleness.sh
→ 6 nodes flagged as potentially stale

Step 3: Parallel Validation (Batch 1)
Task(Validator, src/api/AGENTS.md)
Task(Validator, src/auth/AGENTS.md)
Task(Validator, src/db/AGENTS.md)
Task(Validator, src/models/AGENTS.md)
→ Wait for all 4 to complete
→ Collect results: 2 PASS, 1 WARN, 1 FAIL

Step 4: Parallel Validation (Batch 2)
Task(Validator, src/workers/AGENTS.md)
Task(Validator, src/utils/AGENTS.md)
→ Wait for both to complete
→ Collect results: 1 PASS, 1 WARN

Step 5: Aggregate
→ Total: 3 PASS, 2 WARN, 1 FAIL
→ Generate prioritized report
→ Present recommendations
```

### Example 2: Parallel Exploration (Large Monorepo Setup)

Scenario: Initial Intent Layer setup with 12 candidate directories.

```
Step 1: State Detection
$ ${CLAUDE_PLUGIN_ROOT}/scripts/detect_state.sh
→ State: none
→ 12 candidate directories identified

Step 2: Token Estimation
$ ${CLAUDE_PLUGIN_ROOT}/scripts/estimate_all_candidates.sh
→ 8 directories need nodes (>20k tokens each)
→ 4 directories can be covered by parents (<20k tokens)

Step 3: Parallel Exploration (Batch 1)
Task(Explorer, services/auth/)
Task(Explorer, services/api/)
Task(Explorer, services/payments/)
Task(Explorer, packages/shared/)
→ Wait for all 4 to complete
→ Collect 4 draft proposals

Step 4: Parallel Exploration (Batch 2)
Task(Explorer, services/notifications/)
Task(Explorer, services/analytics/)
Task(Explorer, packages/ui/)
Task(Explorer, infra/)
→ Wait for all 4 to complete
→ Collect 4 more draft proposals

Step 5: Cross-Cutting Analysis
→ Scan all 8 proposals for repeated patterns
→ Identify LCA candidates:
  - "All services use shared logger" → root
  - "Auth via JWT" → services/AGENTS.md
→ Deduplicate before creating nodes

Step 6: Sequential Validation
Task(Validator, aggregated-proposals)
→ Verify accuracy before user review

Step 7: Present to User
→ Show 8 proposed nodes with confidence scores
→ Highlight cross-cutting concerns placed at LCA
→ User reviews and approves
```

### Example 3: Parallel Learning Report Processing

Scenario: Multiple mistake reports accumulated, need processing.

```
Step 1: List Pending Reports
$ ${CLAUDE_PLUGIN_ROOT}/scripts/review_mistakes.sh --list
→ 6 pending mistake reports in different directories

Step 2: Parallel Integration
For each report, find covering node and integrate:
Task(integrate_pitfall, report-1, src/api/AGENTS.md)
Task(integrate_pitfall, report-2, src/api/AGENTS.md)
Task(integrate_pitfall, report-3, src/auth/AGENTS.md)
Task(integrate_pitfall, report-4, src/db/AGENTS.md)
→ Wait for all to complete

Step 3: Validate Affected Nodes
Task(Validator, src/api/AGENTS.md)
Task(Validator, src/auth/AGENTS.md)
Task(Validator, src/db/AGENTS.md)
→ Ensure integrations didn't break anything
```

## Agent-Specific Parallelization Notes

### Explorer

**Can parallelize**: Across independent directories at the same tree level.

**Cannot parallelize**: Parent and child directories (parent may cover child).

```
OK:
  Explorer(src/api/) || Explorer(src/auth/) || Explorer(src/db/)

NOT OK:
  Explorer(src/) || Explorer(src/api/)  # Overlap
```

**Output aggregation**: Merge proposals, deduplicate cross-cutting concerns, identify LCA placements.

### Validator

**Can parallelize**: All independent nodes.

**Dependencies**: None between nodes (each validates against its own covered code).

```
OK:
  Validator(any-node) || Validator(any-other-node)
```

**Output aggregation**: Merge PASS/WARN/FAIL counts, collect all issues, determine overall status (worst of all).

### Auditor

**Parallelizes internally**: Spawns parallel Validators for each discovered node.

**External invocation**: Single Auditor per repository (it handles parallelization).

```
OK:
  Auditor(repo-root)  # Internally spawns parallel Validators

NOT OK:
  Auditor(repo-root) || Auditor(repo-root)  # Redundant
```

**Output**: Single aggregated report covering all nodes.

## Batch Size Guidelines

Limit concurrent agents to avoid resource exhaustion:

| Context | Max Concurrent | Rationale |
|---------|----------------|-----------|
| CI/CD | 2-3 | Shared runners, memory limits |
| Local development | 4-6 | Typical laptop resources |
| Dedicated analysis | 8-10 | Server with resources |

Formula: `batch_size = min(available_agents, resource_limit, task_count)`

## Integration with Skills

### /intent-layer (Initial Setup)

```
1. detect_state.sh → State = none
2. analyze_structure.sh → List candidates
3. If >5 candidates:
   - Parallel Explorer batch
   - Aggregate proposals
   - Sequential Validator on aggregated result
4. Present to user
```

### /intent-layer-maintenance

```
1. detect_staleness.sh → List flagged nodes
2. If >3 flagged:
   - Parallel Validator batch
   - Aggregate results
3. Present prioritized recommendations
```

### Auditor Agent

```
1. show_hierarchy.sh → All nodes
2. detect_staleness.sh → Quick triage
3. Batch parallel Validators (4 at a time)
4. Aggregate into single report
```

## Checklist Before Parallelizing

- [ ] No sequential dependencies between tasks
- [ ] Codebase large enough (>50k tokens or >3 nodes)
- [ ] Tasks are independent (no shared state)
- [ ] Resource limits considered (batch size)
- [ ] Error handling planned (partial failures)
- [ ] Aggregation strategy defined (how to merge results)
