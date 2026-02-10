---
name: intent-layer-compound
description: >
  End-of-cycle learning capture and triage. Run after completing a feature,
  fixing a bug, or finishing any significant work. Reviews pending learnings,
  analyzes conversation for undocumented insights, and integrates into the
  Intent Layer with appropriate scope (global workflow vs local code).
argument-hint: "[/path/to/project]"
---

# Compound Learning Skill

> **TL;DR**: Capture and triage learnings at the end of a work session. Runs conversation analysis, surfaces candidates, and integrates with proper scope routing.

---

## When to Use

Run `/intent-layer-compound` after:
- Completing a feature or bug fix
- Finishing any significant work session
- Discovering non-obvious behaviors or gotchas
- When you want to capture learnings before ending the session

---

## Three-Layer Workflow

### Layer 1: AI Conversation Scan

Before prompting for manual capture, analyze the conversation for learning signals.

**Scan for these patterns:**

| Pattern | Example Phrases | Learning Type |
|---------|-----------------|---------------|
| User corrections | "actually...", "no, you should...", "that's wrong" | pitfall |
| Discoveries | "interesting...", "I didn't know...", "turns out..." | insight |
| Better approaches | "a better way is...", "instead, try..." | pattern |
| Unexpected behaviors | "but it returned...", "weird, it..." | pitfall |
| Missing checks | "should have verified...", "forgot to check..." | check |

**For each candidate found:**
1. Extract the relevant conversation snippet
2. Identify the learning type
3. Determine affected directory (if identifiable from context)
4. Present to user for confirmation

**Example output:**
```
Found 3 potential learnings in this conversation:

1. [pitfall] User corrected assumption about API response format
   Context: "Actually, the API returns a list when there are multiple results..."
   Affected: src/api/

2. [insight] Discovery about caching behavior
   Context: "Turns out the cache invalidates on every deploy..."
   Affected: (workflow-level)

3. [check] Missing verification identified
   Context: "Should have verified the schema before migration..."
   Affected: src/db/
```

### Layer 2: Structured Prompts

After AI-surfaced candidates are reviewed, prompt for additional learnings:

**Prompt sequence:**
1. "Were there any corrections you made to my assumptions?"
2. "Did we discover any unexpected behaviors?"
3. "Are there any better approaches we figured out?"
4. "Any checks that would have helped if done earlier?"

For each "yes" response:
- Use the scan prompt from `prompts/scan.md` to extract details
- Capture via the existing `capture_mistake.sh` with pre-filled fields
- Assign appropriate learning type

### Layer 3: Pending Review

After capture is complete:

1. **Show pending count** (auto-captured + just captured)
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/review_mistakes.sh [PROJECT_PATH]
   ```

2. **Run interactive review** with scope selection
   - For each learning, prompt: `Scope: [l]ocal or [g]lobal [Enter=<default>]?`
   - Smart defaults:
     | Type | Default | Rationale |
     |------|---------|-----------|
     | insight | global | Workflow-level knowledge |
     | pitfall | local | Code-specific gotcha |
     | check | local | Pre-action verification |
     | pattern | local | Usually code patterns |

3. **Show summary** of what was integrated and where

---

## Resources

### Scripts Used

| Script | Purpose |
|--------|---------|
| `capture_mistake.sh` | Create learning report with type selection |
| `review_mistakes.sh` | Interactive triage with scope routing |
| `integrate_pitfall.sh` | Merge accepted learning into covering AGENTS.md |

### Prompts

| Prompt | Purpose |
|--------|---------|
| `prompts/scan.md` | Conversation analysis for learning signals |

---

## Quick Start

```
/intent-layer-compound
```

Or with explicit project path:
```
/intent-layer-compound /path/to/project
```

---

## Example Session

```
$ /intent-layer-compound

=== Intent Layer Compound Learning ===

[Layer 1: Conversation Scan]
Analyzing conversation for potential learnings...

Found 2 potential learnings:

1. [pitfall] API response format varies
   "Actually, the API can return either a dict or a list..."
   Affected: src/api/

   Is this worth documenting? [y/n/edit]: y
   ✓ Captured as PITFALL-2024-01-15-api-response.md

2. [insight] Deploy triggers cache invalidation
   "Turns out the cache clears on every deploy..."
   Affected: (workflow-level)

   Is this worth documenting? [y/n/edit]: y
   ✓ Captured as INSIGHT-2024-01-15-cache-deploy.md

[Layer 2: Additional Prompts]
Any other corrections you made to my assumptions? [y/n]: n
Any unexpected behaviors discovered? [y/n]: n
Any better approaches figured out? [y/n]: n

[Layer 3: Pending Review]
Found 3 pending reports (1 auto-captured, 2 just captured)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[1/3] PITFALL-2024-01-15-api-response.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Directory:  src/api/
Operation:  Parse API response
...

Action [a/r/d/e/s/q/?]: a

Scope: [l]ocal (src/api/AGENTS.md) or [g]lobal (CLAUDE.md)
Select scope [l/g, Enter=local]:

Integrating (local scope)...
✓ pitfall added to ## Pitfalls in src/api/AGENTS.md (local)
✓ Moved to integrated/

...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Review Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Reviewed:  3
  Accepted:  2 (1 local, 1 global)
  Rejected:  0
  Discarded: 1
  Skipped:   0

Compound learning complete!
```

---

## Scope Routing

The compound skill routes learnings to the appropriate location:

```
Learning captured
       │
       └─── Is it workflow-level? (insight, cross-cutting)
                    │
          ┌────────┴────────┐
          │                 │
         Yes                No
          │                 │
          ▼                 ▼
    Root CLAUDE.md    Covering AGENTS.md
    (global scope)    (local scope)
```

### Global Scope (Root CLAUDE.md)

Use for:
- Workflow insights (build process, deployment, testing)
- Cross-cutting patterns that apply everywhere
- Project-wide conventions and decisions
- Learnings that don't belong to any specific directory

### Local Scope (Covering AGENTS.md)

Use for:
- Code-specific pitfalls
- API behavior quirks
- Module-specific patterns
- Checks for particular operations

---

## Integration with Hooks

The compound skill works with the existing learning loop hooks:

- **PostToolUseFailure**: Auto-captures failures → pending/
- **Stop hook**: Prompts for learnings if configured
- **/intent-layer-compound**: End-of-session synthesis

Run `/intent-layer-compound` to process any auto-captured learnings alongside manual capture.
