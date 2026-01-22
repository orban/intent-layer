---
name: pr-review-mining
description: >
  Extract Intent Layer content from GitHub PR descriptions and review comments.
  Mines merged PRs for pitfalls, contracts, architecture decisions, and anti-patterns
  that should be documented in AGENTS.md files.
argument-hint: "[/path/to/directory] [--since <date>] [--limit <count>]"
---

# PR Review Mining

Extract tribal knowledge from GitHub PR discussions to populate Intent Layer nodes.

## Why PR Reviews?

PR descriptions and review comments contain valuable context that commit messages lack:
- **Breaking Changes sections** → Contracts (what invariants changed)
- **"Why" sections** → Architecture Decisions (rationale)
- **Review warnings** → Pitfalls ("don't forget to handle X")
- **Alternatives Considered** → Anti-patterns (what didn't work)
- **Requested Changes** → Contracts (patterns reviewers enforce)

This context is richer than commit messages because PRs capture the *discussion* around changes.

## Quick Start

```bash
# Find merged PRs affecting a directory
gh pr list --state merged --search "path/to/directory" --json number,title,body --limit 50

# Get review comments for a specific PR
gh api repos/{owner}/{repo}/pulls/{number}/comments

# Get review decisions (APPROVE/REQUEST_CHANGES)
gh api repos/{owner}/{repo}/pulls/{number}/reviews
```

---

## Extraction Workflow

### Step 1: Gather PRs

For the target directory, collect merged PRs:

```bash
# Get PR metadata
gh pr list --state merged --search "[directory]" --json number,title,body,mergedAt --limit 100

# For time-bounded search
gh pr list --state merged --search "[directory] merged:>2024-01-01" --json number,title,body --limit 100
```

### Step 2: Parse PR Bodies (Section-Based)

Look for structured sections in PR descriptions:

| PR Section | Intent Layer Section | Signal |
|------------|---------------------|--------|
| `## What` / `## Summary` | Entry Points | What capability was added |
| `## Why` / `## Motivation` | Architecture Decisions | Rationale for change |
| `## Breaking Changes` | Contracts | Invariants that changed |
| `## How to Test` | Entry Points | Verification patterns |
| `## Risks` / `## Concerns` | Pitfalls | Known edge cases |
| `## Alternatives Considered` | Architecture Decisions / Anti-patterns | Why not other approaches |

### Step 3: Extract Review Comments

For each PR, fetch review comments:

```bash
# Top-level review comments
gh api repos/{owner}/{repo}/pulls/{number}/comments --jq '.[].body'

# Review decisions with comments
gh api repos/{owner}/{repo}/pulls/{number}/reviews --jq '.[] | select(.body != "") | .body'
```

Apply keyword fallback to unstructured content.

### Step 4: Keyword Fallback

For comments and unstructured PR bodies:

| Pattern | Target Section | Examples |
|---------|----------------|----------|
| `don't`, `never`, `avoid`, `careful` | Pitfalls | "don't forget to handle null" |
| `instead of`, `rather than`, `we decided` | Architecture Decisions | "we use Redis instead of memcached" |
| `must`, `always`, `required`, `invariant` | Contracts | "auth must happen before DB write" |
| `broke`, `regression`, `caused`, `issue` | Pitfalls | "this caused issues in prod" |
| `reverted`, `rolled back`, `didn't work` | Anti-patterns | "we tried X but rolled back" |
| `breaking`, `migration`, `deprecate` | Contracts | "this is a breaking change" |

### Step 5: Score Confidence

| Confidence | Signal |
|------------|--------|
| **High** | Explicit section match (Breaking Changes, Risks) |
| **High** | REQUEST_CHANGES review with clear pattern |
| **Medium** | Strong keyword match in context |
| **Low** | Weak keyword or ambiguous context |

---

## Parallel PR Analysis

For repos with many PRs, use parallel subagents:

### Parallel by PR Batch

```
Task 1 (Explore): "Mine PRs #1-50 for [directory].
                   Extract: pitfalls from Risks/warnings,
                   contracts from Breaking Changes,
                   decisions from Why/Alternatives.
                   Return as Intent Layer findings."

Task 2 (Explore): "Mine PRs #51-100 for [directory].
                   Extract: pitfalls from Risks/warnings,
                   contracts from Breaking Changes,
                   decisions from Why/Alternatives.
                   Return as Intent Layer findings."
```

### Parallel by Category

```
Task 1 (Explore): "Search PR descriptions for [directory] for Breaking Changes.
                   Extract contracts and invariants.
                   Return with PR numbers and confidence."

Task 2 (Explore): "Search PR review comments for [directory] for warnings.
                   Look for 'don't', 'careful', 'must'.
                   Return as potential Pitfalls."

Task 3 (Explore): "Search PRs for [directory] for Alternatives Considered.
                   Extract architecture decisions and anti-patterns.
                   Return with rationale from PR."
```

---

## Output Format

After analysis, present findings for human review:

```markdown
## PR Review Mining Findings for [directory]

### Potential Pitfalls (from PR discussions)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #234 | Upstream API returns 429 without Retry-After header | Review comment | High |
| #189 | Cache invalidation race when multiple pods restart | PR body (Risks) | High |
| #156 | Don't use DELETE cascade on user table | Review comment | Medium |

### Potential Architecture Decisions (from PR rationale)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #201 | Chose event sourcing over CRUD for audit trail | PR body (Why) | High |
| #178 | Redis over Memcached for pub/sub support | Review thread | Medium |

### Potential Contracts (from breaking changes)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #245 | All API responses must include request_id | PR body (Breaking) | High |
| #198 | Auth tokens must be validated before any DB write | REQUEST_CHANGES | High |

### Potential Anti-patterns (from rejected approaches)

| PR | Finding | Source | Confidence |
|----|---------|--------|------------|
| #212 | Don't store sessions in local memory (doesn't scale) | Alternatives Considered | High |
| #167 | Avoid synchronous calls to payment API | Review comment | Medium |

---

**Review needed**: Human should verify findings before adding to AGENTS.md.
Links: [#234](url) [#189](url) ...
```

---

## Integration with Other Skills

### With intent-layer (setup)

Use pr-review-mining during initial setup alongside git-history:

1. Run structure analysis
2. For each candidate directory:
   - Run git-history analysis (commits)
   - Run pr-review-mining (PR discussions)
3. Merge and deduplicate findings
4. Human reviews and refines

### With git-history (complementary)

| Source | Strength | Weakness |
|--------|----------|----------|
| git-history | Covers all changes | Terse commit messages |
| pr-review-mining | Rich "why" context | Only merged PRs with discussions |

Use both for complete coverage:
- git-history catches changes without PR discussion
- pr-review-mining provides deeper rationale

### With intent-layer-maintenance (audits)

After significant merges:

1. Run `detect_changes.sh` to find affected nodes
2. Mine recent PRs touching those areas
3. Check if new pitfalls/contracts emerged
4. Propose updates based on PR discussions

---

## Limitations

| Limitation | Mitigation |
|------------|------------|
| Squash merges lose PR context | Search by merge commit date range |
| Empty PR descriptions | Fall back to review comments |
| No PR template | Use keyword fallback |
| Private repos | Requires `gh` auth with repo access |
| Rate limits | Use `--limit` flag, batch requests |

---

## Example Session

**Goal**: Populate Pitfalls for `src/api/` directory

**Step 1**: Find relevant PRs

```bash
gh pr list --state merged --search "src/api" --json number,title --limit 20
```

Output:
```
#234  fix: handle null response from payment API
#212  refactor: move to event-driven architecture
#198  feat: add request ID to all responses
```

**Step 2**: Extract from PR #234

```bash
gh pr view 234 --json body
```

Body contains:
```markdown
## Why
The payment API sometimes returns null instead of an error object.

## Risks
- Other upstream APIs might have similar behavior
- Need to audit all external API calls
```

**Step 3**: Extract from review comments

```bash
gh api repos/owner/repo/pulls/234/comments --jq '.[].body'
```

Comment: "Don't forget to add this check to the refund endpoint too"

**Step 4**: Compile findings

```markdown
### Potential Pitfalls

1. **Payment API returns null on error** (#234)
   - Source: PR body (Why section)
   - Confidence: High
   - Note: May affect other upstream APIs

2. **Refund endpoint needs same null check** (#234)
   - Source: Review comment
   - Confidence: High
   - Pattern: All external API calls need null handling
```

**Step 5**: Human review and add to `src/api/AGENTS.md`

---

## Command Reference

```bash
# List merged PRs for directory
gh pr list --state merged --search "[path]" --json number,title,body,mergedAt

# Get PR body
gh pr view [number] --json body,title

# Get review comments
gh api repos/{owner}/{repo}/pulls/{number}/comments

# Get review decisions
gh api repos/{owner}/{repo}/pulls/{number}/reviews

# Search PRs by date
gh pr list --state merged --search "merged:>YYYY-MM-DD [path]"
```
