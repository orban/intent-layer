---
name: intent-layer:review
description: Batch review pending learnings from the Intent Layer learning loop. Rank by confidence, multiSelect for batch acceptance.
argument-hint: "[/path/to/project]"
---

# Intent Layer: Review Pending Learnings

Batch review and triage of pending learning reports. Presents all pending items ranked by confidence for multi-select acceptance.

## Step 1: Scan Pending Reports

```bash
find "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/pending" -name "*.md" -type f 2>/dev/null | sort
```

If no reports found, tell the user:

> Nothing to review. Intent Layer learning queue is empty.

Then stop.

## Step 2: Parse Each Report

For every `.md` file in `pending/`, read it and extract:

- **Title**: from `**Operation**:` line
- **Type**: from `**Type**:` line (pitfall, check, pattern, insight)
- **Confidence**: from `**Confidence**:` line (high, medium, low). Default to "medium" if missing.
- **Covering node**: from `**Covering node**:` or `**Existing node**:` line
- **Timestamp**: from `**Timestamp**:` line
- **Directory**: from `**Directory**:` line

Also read the "What Went Wrong" / "Check Needed" / "Better Approach" / "Key Insight" section body for a one-line summary.

## Step 3: Sort and Rank

Sort items by:
1. Confidence: high > medium > low
2. Within same confidence: newest first (by timestamp)

Assign rank numbers starting from 1.

## Step 4: Present for Review

Build a summary table in your message showing:

```
| # | Conf   | Type    | Title                     | Directory   |
|---|--------|---------|---------------------------|-------------|
| 1 | high   | pitfall | API response can be list  | src/api/    |
| 2 | medium | pattern | Retry needs backoff       | src/api/    |
| 3 | low    | check   | Type narrowing on union   | src/        |
```

Then use `AskUserQuestion` with `multiSelect: true` to let the user select which items to integrate:

- Each option label: `#N: [title]` (short enough for the chip UI)
- Each option description: `[type] — [one-line summary] (confidence: [level])`
- Include an option: "Discard all" with description "Delete all pending reports without integrating"

**If there are more than 4 items**: present only the top 4 by confidence in the AskUserQuestion options. After processing those, loop back to Step 1 for remaining items.

## Step 5: Integrate Selected Items

For each selected item, run `learn.sh`:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/learn.sh \
    --project "${CLAUDE_PROJECT_DIR:-.}" \
    --path "<directory from report>" \
    --type "<type from report>" \
    --title "<title from report>" \
    --detail "<detail/body from report>"
```

**Handle results:**
- Exit 0 → integrated. Delete the report file from `pending/`.
- Exit 2 → duplicate (already documented). Delete the report file. Note as "already known" in summary.
- Other exit → integration failed. Leave report in `pending/`. Note the failure in summary.

## Step 6: Handle Unselected Items

Leave unselected items in `pending/`. They'll appear in the next review.

If "Discard all" was selected, delete all pending reports:
```bash
rm -f "${CLAUDE_PROJECT_DIR:-.}/.intent-layer/mistakes/pending/"*.md
```

## Step 7: Summary

Show a brief summary:

```
Review complete:
  Integrated: N
  Already known: N
  Failed: N
  Deferred: N (still in pending/)
  Discarded: N
```

If any items failed integration, suggest running `/intent-layer:review` again after fixing the underlying issue (usually a missing covering AGENTS.md node).

---

## Notes

- This skill replaces the old `review-mistakes` skill and `intent-layer-compound` end-of-session capture
- The stop hook auto-captures learnings with confidence scores — this skill is where humans triage them
- High-confidence learnings from the stop hook may already be auto-integrated via `learn.sh`. Those won't appear here.
- Reports include skeleton reports from tool failures and full reports from manual capture
