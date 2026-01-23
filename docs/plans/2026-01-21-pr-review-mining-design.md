# PR Review Mining Design

> Extract intent from GitHub PR descriptions and review comments to populate Intent Layer nodes.

## Overview

New sub-skill `pr-review-mining` that mines merged PRs for tribal knowledge. Complements `git-history` by capturing richer "why" context from PR discussions.

## Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Platform | GitHub only (`gh` CLI) | Consistent with git-history, covers most cases |
| Data sources | PR descriptions + review comments | Rich signal without line-comment noise |
| Categorization | Section-based + keyword fallback | Leverages PR templates, degrades gracefully |
| Output | Table format | Matches git-history for consistency |

## Data Sources

### PR Descriptions

```bash
gh pr list --state merged --json number,title,body,mergedAt --limit 100
```

### Review Comments

```bash
# Top-level review comments
gh api repos/{owner}/{repo}/pulls/{number}/comments

# Review decisions (APPROVE/REQUEST_CHANGES)
gh api repos/{owner}/{repo}/pulls/{number}/reviews
```

## Categorization Logic

### Section-Based (PR Bodies)

| PR Section | Intent Layer Section |
|------------|---------------------|
| `## What` / `## Summary` | Entry Points |
| `## Why` / `## Motivation` | Architecture Decisions |
| `## Breaking Changes` | Contracts |
| `## How to Test` | Entry Points |
| `## Risks` / `## Concerns` | Pitfalls |
| `## Alternatives Considered` | Architecture Decisions |

### Keyword Fallback (Comments & Unstructured)

| Pattern | Target Section |
|---------|----------------|
| `don't`, `never`, `avoid`, `careful` | Pitfalls |
| `instead of`, `rather than`, `we decided` | Architecture Decisions |
| `must`, `always`, `required`, `invariant` | Contracts |
| `broke`, `regression`, `caused`, `issue` | Pitfalls |
| `reverted`, `rolled back`, `didn't work` | Anti-patterns |

### Confidence Scoring

- **High**: Explicit section match or strong keyword + context
- **Medium**: Keyword match in relevant context
- **Low**: Weak signal, needs human review

## Output Format

```markdown
## PR Review Mining Findings for [directory]

### Potential Pitfalls (from PR discussions)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #234 | Upstream API returns 429 without Retry-After | Review comment | High |

### Potential Architecture Decisions (from PR rationale)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #201 | Chose event sourcing over CRUD for audit trail | PR body (Why) | High |

### Potential Contracts (from breaking changes)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #245 | All API responses must include request_id | PR body (Breaking) | High |

### Potential Anti-patterns (from rejected approaches)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #212 | Don't store sessions in local memory | Alternatives Considered | High |

---

**Review needed**: Human should verify before adding to AGENTS.md.
```

## Usage

```bash
# Basic: mine PRs affecting a directory
/pr-review-mining src/api/

# With time bounds
/pr-review-mining src/api/ --since 2024-01-01

# Limit PR count
/pr-review-mining src/api/ --limit 50
```

## Integration

| Skill | How |
|-------|-----|
| `intent-layer` (setup) | Auto-invoked alongside git-history |
| `intent-layer-maintenance` | Run after merges for undocumented decisions |
| `git-history` | Complements - PRs have richer "why" |

## Files

**Create:**
- `intent-layer/pr-review-mining/SKILL.md`

**Update:**
- `intent-layer/SKILL.md` - add auto-invoke
