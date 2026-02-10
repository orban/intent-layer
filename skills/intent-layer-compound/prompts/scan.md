# Conversation Analysis Prompt

Analyze the conversation for potential learnings that should be documented in the Intent Layer.

## What to Look For

### 1. User Corrections
Where the user corrected an assumption or approach.

**Signal phrases:**
- "actually..."
- "no, you should..."
- "that's wrong"
- "not quite..."
- "it's the other way around"
- "you need to do X first"

**Learning type:** Usually `pitfall` (wrong assumption) or `check` (missing verification)

### 2. Discoveries
Unexpected behaviors, edge cases, or gotchas found during the work.

**Signal phrases:**
- "interesting..."
- "I didn't know..."
- "turns out..."
- "surprisingly..."
- "that's weird..."
- "but it actually..."

**Learning type:** Usually `pitfall` (gotcha) or `insight` (useful discovery)

### 3. Better Approaches
Improved patterns or methods discovered.

**Signal phrases:**
- "a better way is..."
- "instead, try..."
- "the proper way..."
- "you should use X instead of Y"
- "the pattern we use is..."

**Learning type:** Usually `pattern` (preferred approach)

### 4. Missing Checks
Verification or validation that would have helped earlier.

**Signal phrases:**
- "should have checked..."
- "forgot to verify..."
- "need to make sure..."
- "always check X before Y"
- "this would have caught it"

**Learning type:** `check` (pre-action verification)

## Output Format

For each potential learning, extract:

```markdown
## Candidate [N]

**Type**: pitfall | check | pattern | insight
**Quote**: "[The relevant conversation snippet]"
**Summary**: [One-line description of the learning]
**Affected area**: [Directory path if identifiable, or "(workflow-level)" if cross-cutting]
**Confidence**: high | medium | low
```

## Confidence Levels

- **High**: User explicitly stated a correction or learning
- **Medium**: Clear signal phrase with actionable content
- **Low**: Implicit learning, may need clarification

## Examples

### Example 1: User Correction (High Confidence)

Conversation:
> User: "Actually, the API can return either a dict or a list depending on the query type. You need to check the type before calling .get()."

Extracted:
```markdown
## Candidate 1

**Type**: pitfall
**Quote**: "Actually, the API can return either a dict or a list depending on the query type. You need to check the type before calling .get()."
**Summary**: API response format varies by query type - check isinstance before .get()
**Affected area**: src/api/ (inferred from context)
**Confidence**: high
```

### Example 2: Discovery (Medium Confidence)

Conversation:
> User: "Turns out the cache invalidates automatically on every deploy. That's why the first request after deploy is slow."

Extracted:
```markdown
## Candidate 2

**Type**: insight
**Quote**: "Turns out the cache invalidates automatically on every deploy. That's why the first request after deploy is slow."
**Summary**: Cache invalidates on deploy, causing slow first requests
**Affected area**: (workflow-level)
**Confidence**: medium
```

### Example 3: Missing Check (High Confidence)

Conversation:
> User: "We should have verified the schema exists before running the migration. Always check with `hasattr(db, 'schema_version')` first."

Extracted:
```markdown
## Candidate 3

**Type**: check
**Quote**: "We should have verified the schema exists before running the migration. Always check with `hasattr(db, 'schema_version')` first."
**Summary**: Before migration, verify schema_version exists
**Affected area**: src/db/
**Confidence**: high
```

## What NOT to Extract

Skip these as they're not learnings:

- General acknowledgments ("Got it", "Okay")
- Standard programming knowledge
- Things already documented in AGENTS.md
- Temporary workarounds being removed
- User preferences that aren't universal

## Processing Order

1. Scan entire conversation chronologically
2. Extract all candidates
3. Deduplicate (same learning mentioned multiple times)
4. Rank by confidence (high first)
5. Present to user for confirmation
