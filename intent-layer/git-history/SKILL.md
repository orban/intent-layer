---
name: git-history
description: >
  Extract Intent Layer content from git history. Analyzes commits, PRs, and
  blame to discover pitfalls, contracts, architecture decisions, and entry points
  that should be documented in AGENTS.md files.
argument-hint: "[/path/to/directory] [--since <date>] [--depth <commits>]"
---

# Git History Analysis

Extract tribal knowledge from git history to populate Intent Layer nodes.

## Why Git History?

Commit messages and PR descriptions contain valuable context:
- **Bug fixes** → Pitfalls (what went wrong, what surprised people)
- **Reverts** → Anti-patterns (what didn't work)
- **Refactors** → Architecture decisions (why structure changed)
- **Feature commits** → Entry points (where new things get added)
- **"Fix" commits** → Contracts (invariants that were violated)

This context is often lost when engineers leave or memories fade.

## Quick Start

```bash
# Analyze recent history for a directory
git log --oneline --since="6 months ago" -- path/to/directory

# Find bug fixes (likely pitfalls)
git log --oneline --grep="fix" --grep="bug" --all-match -- path/to/directory

# Find reverts (likely anti-patterns)
git log --oneline --grep="revert" -i -- path/to/directory

# Find refactors (likely architecture decisions)
git log --oneline --grep="refactor" -i -- path/to/directory
```

---

## Extraction Workflow

### Step 1: Gather Raw History

For the target directory, collect:

```bash
# All commits with full messages
git log --since="1 year ago" --pretty=format:"%h|%s|%b---" -- [directory]

# Commits that mention "fix", "bug", "broken", "issue"
git log --since="1 year ago" --grep="fix\|bug\|broken\|issue" -i --pretty=format:"%h|%s" -- [directory]

# Commits that mention "revert", "rollback", "undo"
git log --since="1 year ago" --grep="revert\|rollback\|undo" -i --pretty=format:"%h|%s" -- [directory]

# Commits with "BREAKING", "breaking change", "migration"
git log --since="1 year ago" --grep="BREAKING\|breaking change\|migration" -i --pretty=format:"%h|%s" -- [directory]
```

### Step 2: Categorize by Intent Layer Section

| Commit Pattern | Target Section | Signal |
|----------------|----------------|--------|
| `fix:`, `bug`, `broken` | Pitfalls | Something surprised someone |
| `revert`, `rollback` | Anti-patterns | Something didn't work |
| `refactor:`, `restructure` | Architecture Decisions | Design changed |
| `feat:`, `add`, `implement` | Entry Points | New capability added |
| `BREAKING`, `migration` | Contracts | Invariant changed |
| `docs:`, `update readme` | (verify existing docs) | May need refresh |
| `perf:`, `optimize` | Pitfalls or Patterns | Performance matters here |
| `security:`, `auth`, `vulnerability` | Contracts | Security invariant |

### Step 3: Extract Insights

For each relevant commit, extract:

**For Pitfalls:**
```markdown
- [What the fix addressed] - discovered in [commit hash]
  - Original issue: [from commit message]
  - Why it was surprising: [infer from context]
```

**For Anti-patterns:**
```markdown
- Don't [what was reverted] - reverted in [commit hash]
  - Why it failed: [from revert message or PR]
```

**For Architecture Decisions:**
```markdown
- [Decision]: [rationale from refactor commit]
  - Changed in: [commit hash]
  - Previous approach: [if mentioned]
```

**For Contracts:**
```markdown
- [Invariant] - established/changed in [commit hash]
  - Breaking change note: [from commit]
```

---

## Parallel History Analysis

For large directories or deep history, use parallel subagents:

### Parallel Category Search

```
Task 1 (Explore): "Search git history for [directory] for bug fixes.
                   Find commits with 'fix', 'bug', 'broken', 'issue'.
                   Extract: what broke, why, what the fix was.
                   Return as potential Pitfalls entries."

Task 2 (Explore): "Search git history for [directory] for reverts.
                   Find commits with 'revert', 'rollback', 'undo'.
                   Extract: what was reverted, why it failed.
                   Return as potential Anti-patterns entries."

Task 3 (Explore): "Search git history for [directory] for refactors.
                   Find commits with 'refactor', 'restructure', 'reorganize'.
                   Extract: what changed, why, what was the previous approach.
                   Return as potential Architecture Decisions entries."

Task 4 (Explore): "Search git history for [directory] for breaking changes.
                   Find commits with 'BREAKING', 'migration', 'contract'.
                   Extract: what invariant changed, what consumers need to know.
                   Return as potential Contracts entries."
```

### Parallel Time-Range Analysis

For very deep history:

```
Task 1: "Analyze git history for [directory] from 2024-01 to 2024-06.
         Categorize commits by Intent Layer section."

Task 2: "Analyze git history for [directory] from 2024-07 to 2024-12.
         Categorize commits by Intent Layer section."

Task 3: "Analyze git history for [directory] from 2023-01 to 2023-12.
         Categorize commits by Intent Layer section."
```

---

## Advanced Techniques

### Git Blame for Hot Spots

Find files with most churn (likely complex/pitfall-prone):

```bash
# Files with most commits (complexity signal)
git log --since="1 year ago" --pretty=format: --name-only -- [directory] | \
  sort | uniq -c | sort -rn | head -20

# Recent blame for specific file (who knows this code)
git blame --since="6 months ago" [file] | \
  awk '{print $2}' | sort | uniq -c | sort -rn
```

### PR/MR Description Mining

If using GitHub:

```bash
# Get PR descriptions for merged PRs affecting directory
gh pr list --state merged --search "[directory]" --json title,body,number --limit 50
```

Extract from PR descriptions:
- "This PR fixes..." → Pitfalls
- "Breaking change:" → Contracts
- "This replaces..." → Architecture Decisions
- "How to test:" → Entry Points (verification patterns)

### Commit Message Conventions

If the repo uses conventional commits, leverage the prefixes:

| Prefix | Intent Layer Section |
|--------|---------------------|
| `fix:` | Pitfalls |
| `feat:` | Entry Points |
| `refactor:` | Architecture Decisions |
| `perf:` | Pitfalls (performance) |
| `security:` | Contracts |
| `revert:` | Anti-patterns |
| `BREAKING CHANGE:` | Contracts |

---

## Output Format

After analysis, present findings for human review:

```markdown
## Git History Findings for [directory]

### Potential Pitfalls (from bug fixes)

| Commit | Finding | Confidence |
|--------|---------|------------|
| abc123 | Config reload doesn't pick up env var changes | High (explicit fix) |
| def456 | Race condition when multiple workers start | Medium (inferred) |

### Potential Anti-patterns (from reverts)

| Commit | Finding | Confidence |
|--------|---------|------------|
| ghi789 | Don't use global state for request context | High (reverted) |

### Potential Architecture Decisions (from refactors)

| Commit | Finding | Confidence |
|--------|---------|------------|
| jkl012 | Moved to event-driven updates (from polling) | High (explicit refactor) |

### Potential Contracts (from breaking changes)

| Commit | Finding | Confidence |
|--------|---------|------------|
| mno345 | All handlers must return structured errors | High (BREAKING) |

---

**Review needed**: Human should verify these findings before adding to AGENTS.md.
Some may be outdated, fixed differently, or no longer relevant.
```

---

## Integration with Other Skills

### With intent-layer (setup)

Use git-history during initial setup to pre-populate nodes:

1. Run structure analysis
2. For each candidate directory, run git-history analysis
3. Pre-fill Pitfalls and Architecture Decisions from history
4. Human reviews and refines

### With intent-layer-maintenance (audits)

Use git-history to find undocumented changes:

1. Run `detect_changes.sh` to find affected nodes
2. For affected directories, analyze recent git history
3. Check if new pitfalls/contracts emerged since last audit
4. Propose updates based on commit analysis

### With intent-layer-query

When query returns "uncertain" confidence:

1. Fall back to git history for the area
2. Search for commits mentioning the concept
3. Extract context from historical changes
4. Flag as "inferred from history" with commit references

---

## Limitations

| Limitation | Mitigation |
|------------|------------|
| Poor commit messages | Supplement with PR descriptions if available |
| Squash merges lose detail | Check PR/MR descriptions for context |
| Old history may be irrelevant | Default to recent (1 year) history |
| False positives | Always require human review before adding |
| Missing context | Flag confidence level, cite commit hash |

---

## Example Session

**Goal**: Populate Pitfalls for `src/api/` directory

**Step 1**: Search for bug fixes
```bash
git log --since="1 year ago" --grep="fix" -i --oneline -- src/api/
```

Output:
```
a1b2c3d fix: handle null response from upstream service
e4f5g6h fix: rate limiter not resetting after window
i7j8k9l fix: auth token validation skipped for internal routes
```

**Step 2**: Extract insights

```markdown
### Potential Pitfalls

1. **Upstream service can return null** (a1b2c3d)
   - The external payment API sometimes returns null instead of error
   - Must check for null before accessing response fields

2. **Rate limiter window edge case** (e4f5g6h)
   - Rate limit counter doesn't reset exactly at window boundary
   - Can cause brief period of incorrect rate limiting

3. **Internal routes bypass auth** (i7j8k9l)
   - Routes marked "internal" skip token validation
   - If internal route exposed externally, auth is bypassed
```

**Step 3**: Human review and add to `src/api/AGENTS.md`

---

## Scripts Reference

This skill primarily uses git commands directly. Useful aliases:

```bash
# Add to ~/.gitconfig
[alias]
  pitfalls = log --since='1 year ago' --grep='fix\\|bug\\|broken' -i --oneline
  antipatterns = log --since='1 year ago' --grep='revert\\|rollback' -i --oneline
  decisions = log --since='1 year ago' --grep='refactor\\|restructure' -i --oneline
  contracts = log --since='1 year ago' --grep='BREAKING\\|migration' -i --oneline
```

Usage:
```bash
git pitfalls -- src/api/
git antipatterns -- src/api/
git decisions -- src/api/
git contracts -- src/api/
```
