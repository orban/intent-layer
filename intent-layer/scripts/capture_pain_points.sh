#!/usr/bin/env bash
# Generate a pain points capture template for Intent Layer maintenance
# Usage: ./capture_pain_points.sh [output_file]
#
# Creates a structured markdown file for recording findings.
# Fill in the template, then use map_findings.sh to generate update proposals.

set -e

OUTPUT_FILE="${1:-pain_points_capture.md}"
TIMESTAMP=$(date +"%Y-%m-%d")

cat > "$OUTPUT_FILE" << 'TEMPLATE'
# Intent Layer Pain Points Capture

> Fill in findings below. Delete sections with no findings.
> When done, this file feeds into the update proposal.

## Metadata

- **Date**: TIMESTAMP_PLACEHOLDER
- **Reviewer**:
- **Project**:

---

## Recent Pitfalls

> Things that surprised you or caught someone off guard.
> These map to the **Pitfalls** section in CLAUDE.md.

### What surprised you in the last 3 months?

<!-- Example: The `config/legacy.json` file looks unused but controls enterprise feature flags -->


### What looked deprecated/unused but actually wasn't?

<!-- Example: `utils/old_parser.py` is still used by the batch processing system -->


### What broke silently when someone made a reasonable assumption?

<!-- Example: Deleting "unused" CSS variables broke the dark mode toggle -->


### What implicit assumption bit someone?

<!-- Example: Tests assume UTC timezone but CI runs in PST -->


---

## Contract Violations

> Rules that were broken or need to be documented.
> These map to **Contracts & Invariants** section.

### Did any invariant get violated? Should we document it?

<!-- Example: API v2 started returning 404 instead of 400 for missing resources -->


### Did external consumers break because of API changes?

<!-- Example: Mobile app v2.3 broke when we changed the auth token format -->


### Are there new 'must never happen' rules?

<!-- Example: Never delete a user record - always soft-delete with `deleted_at` -->


---

## Architecture Changes

> Technical decisions or structural changes.
> These map to **Architecture Decisions** section.

### Were any significant technical decisions made?

<!-- Example: Switched from REST to GraphQL for the mobile API -->


### Should we link to new ADRs or design docs?

<!-- Example: ADR-015 documents the caching strategy change -->


### Did subsystem boundaries shift?

<!-- Example: Payment processing moved from monolith to separate service -->


---

## Entry Point Changes

> New tasks or renamed/moved entry points.
> These map to **Entry Points** table.

### Are there new common tasks that need routing?

<!-- Example: "Add a new payment provider" is now a common task -->


### Did any entry points move or get renamed?

<!-- Example: `scripts/deploy.sh` moved to `ops/deploy/` -->


---

## Summary

> After filling in above, summarize the HIGH and MEDIUM priority items.

### High Priority (affects multiple people, causes confusion monthly)

1.
2.
3.

### Medium Priority (found by 1 person, confuses new team members)

1.
2.
3.

### Low Priority (interesting but not decision-making)

1.
2.
3.

---

## Section Mapping

> Reference for where findings should go in CLAUDE.md:

| Finding Type | Target Section |
|--------------|----------------|
| Surprising behavior | Pitfalls |
| "Never do X" rule | Anti-patterns |
| Must-be-true constraint | Contracts & Invariants |
| Technical decision rationale | Architecture Decisions |
| New common task | Entry Points |
| New subsystem | Subsystem Boundaries |
| Relationship to external | Related Context |
TEMPLATE

# Replace timestamp placeholder
sed -i '' "s/TIMESTAMP_PLACEHOLDER/$TIMESTAMP/" "$OUTPUT_FILE" 2>/dev/null || \
sed -i "s/TIMESTAMP_PLACEHOLDER/$TIMESTAMP/" "$OUTPUT_FILE"

echo "=== Pain Points Capture Template Created ==="
echo ""
echo "Output: $OUTPUT_FILE"
echo ""
echo "Next steps:"
echo "1. Fill in the template with findings from team discussions"
echo "2. Prioritize items in the Summary section"
echo "3. Use the Section Mapping table to update CLAUDE.md"
echo ""
echo "Tip: Delete sections that have no findings to keep the document focused."
