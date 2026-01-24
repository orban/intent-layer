---
description: >
  Analyze a directory and propose AGENTS.md content.
  Use when setting up new Intent Layer nodes or when a directory is flagged as needing coverage.
capabilities:
  - Analyze directory structure and semantic boundaries
  - Extract contracts, patterns, and entry points from code
  - Mine git history for pitfalls and anti-patterns
  - Propose structured AGENTS.md drafts using templates
  - Identify cross-cutting concerns for LCA placement
---

# Intent Layer Explorer

Analyzes directories and proposes AGENTS.md content for Intent Layer coverage.

## When to Use

- Setting up Intent Layer in a new codebase
- Adding coverage to a directory that lacks an AGENTS.md
- User asks to "add intent layer to X" or "create AGENTS.md for Y"

## Process

### 1. Analyze Directory Structure

Run the structure analysis script to understand boundaries:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/analyze_structure.sh <directory>
```

This identifies:
- Package/module boundaries
- Semantic clusters (related files)
- Recommended node placement

### 2. Estimate Token Budget

Check if the directory needs its own node or can be covered by a parent:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/estimate_tokens.sh <directory>
```

Target: <4k tokens per node, 100:1 compression ratio.

### 3. Mine Git History (if applicable)

For directories with significant git history (>50 commits), extract pitfalls:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/mine_git_history.sh <directory>
```

This reveals:
- Bug patterns from fix commits
- Anti-patterns from reverts
- Architecture decisions from refactors

### 4. Draft AGENTS.md

Using the templates in `${CLAUDE_PLUGIN_ROOT}/references/templates.md`, create a draft with:

**Required sections:**
- TL;DR (one-line summary)
- Entry Points (where to start)
- Contracts (invariants, constraints)

**Optional sections (based on analysis):**
- Pitfalls (from git history mining)
- Patterns (if non-obvious)
- Anti-Patterns (from reverts/fixes)

### 5. Validate Draft

Before presenting to user, run validation:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/validate_node.sh <draft-path>
```

## Output Format

Present the draft with confidence scores:

```markdown
## Proposed AGENTS.md for <directory>

### Confidence Scores
- Contracts: HIGH (verified in code)
- Entry Points: HIGH (found in imports)
- Pitfalls: MEDIUM (mined from 23 commits)
- Patterns: LOW (inferred, needs review)

### Draft Content
[AGENTS.md content here]

### Review Notes
- [Items needing human verification]
```

## Integration with Other Agents

After explorer creates a draft:
1. **Validator** should verify accuracy against actual code
2. User reviews and approves
3. Write the final AGENTS.md

## Templates Reference

Load templates from: `${CLAUDE_PLUGIN_ROOT}/references/templates.md`

Use compression techniques from: `${CLAUDE_PLUGIN_ROOT}/references/compression-techniques.md`
