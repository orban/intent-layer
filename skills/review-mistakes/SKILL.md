---
name: review-mistakes
description: >
  Interactive review of pending mistake reports from the learning loop.
  Walk through each report with the user, accepting/rejecting/discarding as appropriate.
argument-hint: "[/path/to/project]"
---

# Review Mistakes

Interactively review pending mistake reports from the Intent Layer learning loop.

## Overview

When agents make mistakes during development, skeleton reports are auto-captured in `.intent-layer/mistakes/pending/`. This skill helps you and the user review these reports conversationally, deciding which should become pitfalls in the Intent Layer.

## Prerequisites

Check for pending reports:
```bash
ls -la ${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/pending/
```

## Workflow

### Step 1: List Pending Reports

```bash
find "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/pending" \
  \( -name "MISTAKE-*.md" -o -name "SKELETON-*.md" \) \
  -type f 2>/dev/null | sort
```

If no reports, inform the user there's nothing to review.

### Step 2: For Each Report

Read the report and present a summary:

```markdown
---
**Report**: SKELETON-2026-01-23-1234.md

**Directory**: src/auth/
**Operation**: Edit on login.ts
**What happened**: Tool Edit failed - old_string not found
**Covering node**: src/auth/AGENTS.md

**Analysis**: [Your assessment - is this a real mistake or exploratory?]
---
```

### Step 3: Ask User Decision

Present options clearly:

> **What would you like to do with this report?**
>
> 1. **Accept** - This is a real gotcha, add as pitfall to AGENTS.md
> 2. **Reject** - Not useful (I'll ask for a reason)
> 3. **Discard** - Exploratory failure, not a real mistake
> 4. **Enrich** - Add more context before deciding
> 5. **Skip** - Review later

### Step 4: Execute Decision

#### On Accept

Run the integration script:

```bash
${CLAUDE_PLUGIN_ROOT}/lib/integrate_pitfall.sh "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/pending/<filename>"
```

This will:
- Find the covering AGENTS.md
- Extract/generate a pitfall entry
- Append to the Pitfalls section
- Move report to `integrated/`

#### On Reject

Ask for rejection reason, then:

```bash
# Create rejected directory if needed
mkdir -p "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/rejected"

# Add rejection reason to file
echo -e "\n### Rejection\n**Reason**: <reason>\n**Date**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "<file>"

# Move to rejected
mv "<file>" "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/rejected/"
```

#### On Discard

Simply delete the skeleton:

```bash
rm "<file>"
```

Confirm to user: "Discarded - this was an exploratory failure, not a real mistake."

#### On Enrich

Open the file for editing or help the user add:
- Better description of what went wrong
- Root cause analysis
- Suggested pitfall text

Then return to Step 3.

#### On Skip

Move to the next report. Track skipped files to mention at the end.

### Step 5: Summary

After reviewing all reports (or when user wants to stop):

```markdown
## Review Summary

- **Accepted**: 2 (pitfalls added to AGENTS.md)
- **Rejected**: 1
- **Discarded**: 3 (exploratory failures)
- **Skipped**: 1 (still pending)

Remaining pending: 1 report(s)
```

---

## Report Types

### Skeleton Reports (SKELETON-*.md)

Auto-created by PostToolUseFailure hook. Contains:
- Tool and file context
- Placeholder fields for root cause and suggested fix
- Often exploratory failures - review carefully

**Common skeleton dispositions:**
- **Discard** if: Edit failed because string wasn't found (typo, wrong file)
- **Discard** if: Bash command failed during exploration
- **Accept** if: Failure revealed a non-obvious gotcha about the codebase
- **Enrich then Accept** if: Real mistake but needs better description

### Full Reports (MISTAKE-*.md)

Created manually via `capture_mistake.sh`. Contains:
- Detailed description from human/agent
- Root cause analysis
- Suggested fix

**Common full report dispositions:**
- **Accept** if: Well-documented, clear pitfall
- **Reject** if: One-off issue, not worth documenting
- **Enrich then Accept** if: Good insight but needs clearer pitfall text

---

## Example Conversation

**Agent**: "I found 3 pending mistake reports. Would you like to review them now?"

**User**: "yes"

**Agent**:
> ---
> **Report**: SKELETON-2026-01-23-4521.md
>
> **Directory**: src/api/
> **Operation**: Edit on routes.ts
> **What happened**: Edit failed - old_string not found
> **Covering node**: src/api/AGENTS.md
>
> **Analysis**: This looks like the Edit tool couldn't find the exact string to replace. This could be:
> - A typo in the old_string (exploratory)
> - The file had been modified and the string changed (possible gotcha)
> ---
>
> What would you like to do? (1) Accept (2) Reject (3) Discard (4) Enrich (5) Skip

**User**: "3 - it was just a typo"

**Agent**: "Discarded. Moving to next report..."

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `lib/integrate_pitfall.sh` | Auto-add pitfall to covering AGENTS.md |
| `scripts/capture_mistake.sh` | Manual capture (if needed) |

All paths: `${CLAUDE_PLUGIN_ROOT}/`

---

## Tips

- **Be conservative with Accept** - Only document genuine gotchas that would trip up future agents
- **Discard freely** - Most skeletons from exploratory failures should be discarded
- **Enrich before Accept** - A well-written pitfall is more useful than a vague one
- **Batch review** - Review all pending reports periodically rather than one at a time
