# PR Review Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build PR review tooling that helps humans review AI-generated PRs and AI review human PRs using the Intent Layer as the source of truth.

**Architecture:** A bash script (`review_pr.sh`) handles analysis and output generation. A skill (`pr-review/SKILL.md`) orchestrates interactive review sessions. The script builds on `detect_changes.sh` for finding affected nodes.

**Tech Stack:** Bash (coreutils, grep, awk, sed), optional `gh` CLI for GitHub integration.

---

## Task 1: Create review_pr.sh Core Structure

**Files:**
- Create: `intent-layer/scripts/review_pr.sh`

**Step 1: Create script with help and argument parsing**

```bash
#!/usr/bin/env bash
# Review a PR against the Intent Layer
# Usage: ./review_pr.sh [OPTIONS] [BASE_REF] [HEAD_REF]

set -euo pipefail

VERSION="1.0.0"

show_help() {
    cat << 'EOF'
review_pr.sh - Review PR against Intent Layer

USAGE:
    review_pr.sh [OPTIONS] [BASE_REF] [HEAD_REF]

ARGUMENTS:
    BASE_REF    Git ref to compare from (default: origin/main)
    HEAD_REF    Git ref to compare to (default: HEAD)

OPTIONS:
    -h, --help          Show this help message
    -v, --version       Show version
    --pr NUMBER         Fetch GitHub PR metadata (requires gh CLI)
    --ai-generated      Enable AI-generated code checks
    --summary           Output Layer 1 only (risk score)
    --checklist         Output Layers 1+2 (score + checklist)
    --full              Output all layers (default)
    --exit-code         Exit with code based on risk level (0=low, 1=medium, 2=high)
    --output FILE       Write output to file instead of stdout

EXAMPLES:
    review_pr.sh main HEAD
    review_pr.sh main HEAD --pr 123 --ai-generated
    review_pr.sh --summary
    review_pr.sh main HEAD --exit-code
EOF
    exit 0
}

show_version() {
    echo "review_pr.sh version $VERSION"
    exit 0
}

# Defaults
BASE_REF=""
HEAD_REF="HEAD"
PR_NUMBER=""
AI_GENERATED=false
OUTPUT_MODE="full"
EXIT_CODE_MODE=false
OUTPUT_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -v|--version)
            show_version
            ;;
        --pr)
            PR_NUMBER="$2"
            shift 2
            ;;
        --ai-generated)
            AI_GENERATED=true
            shift
            ;;
        --summary)
            OUTPUT_MODE="summary"
            shift
            ;;
        --checklist)
            OUTPUT_MODE="checklist"
            shift
            ;;
        --full)
            OUTPUT_MODE="full"
            shift
            ;;
        --exit-code)
            EXIT_CODE_MODE=true
            shift
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            echo "Run with --help for usage information" >&2
            exit 1
            ;;
        *)
            if [ -z "$BASE_REF" ]; then
                BASE_REF="$1"
            elif [ "$HEAD_REF" = "HEAD" ]; then
                HEAD_REF="$1"
            else
                echo "Error: Too many arguments" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# Default base ref
if [ -z "$BASE_REF" ]; then
    BASE_REF="origin/main"
fi

echo "PR Review Mode - review_pr.sh v$VERSION"
echo "Comparing: $BASE_REF..$HEAD_REF"
```

**Step 2: Make script executable and test help**

Run: `chmod +x intent-layer/scripts/review_pr.sh && ./intent-layer/scripts/review_pr.sh --help`
Expected: Help message displays correctly

**Step 3: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add review_pr.sh core structure with argument parsing"
```

---

## Task 2: Add Changed Files Detection

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add git validation and changed files detection**

Add after argument parsing:

```bash
# Validate git repository
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Error: Not in a git repository" >&2
    exit 1
}
cd "$REPO_ROOT"

# Validate refs
if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $BASE_REF" >&2
    exit 1
fi
if ! git rev-parse --verify "$HEAD_REF" >/dev/null 2>&1; then
    echo "Error: Invalid git ref: $HEAD_REF" >&2
    exit 1
fi

# Get changed files
CHANGED_FILES=$(git diff --name-only "$BASE_REF" "$HEAD_REF" 2>/dev/null) || {
    echo "Error: Failed to get diff" >&2
    exit 1
}

if [ -z "$CHANGED_FILES" ]; then
    echo "No changed files detected."
    exit 0
fi

FILE_COUNT=$(echo "$CHANGED_FILES" | grep -v '^$' | wc -l | tr -d ' ')
echo "Changed files: $FILE_COUNT"
```

**Step 2: Test with actual git refs**

Run: `./intent-layer/scripts/review_pr.sh HEAD~1 HEAD`
Expected: Shows changed file count

**Step 3: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add git validation and changed files detection"
```

---

## Task 3: Add Intent Node Discovery

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add function to find covering node and map files to nodes**

Add after changed files detection:

```bash
# Find covering Intent Node for a file
find_covering_node() {
    local file="$1"
    local dir=$(dirname "$file")

    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
        if [ -f "$dir/AGENTS.md" ]; then
            echo "$dir/AGENTS.md"
            return
        fi
        if [ -f "$dir/CLAUDE.md" ]; then
            echo "$dir/CLAUDE.md"
            return
        fi
        dir=$(dirname "$dir")
    done

    # Check root
    if [ -f "AGENTS.md" ]; then
        echo "AGENTS.md"
    elif [ -f "CLAUDE.md" ]; then
        echo "CLAUDE.md"
    fi
}

# Map changed files to covering nodes
declare -A NODE_FILES
declare -A NODE_CONTENT

while IFS= read -r file; do
    [ -z "$file" ] && continue
    [[ "$file" == *"AGENTS.md" ]] || [[ "$file" == *"CLAUDE.md" ]] && continue

    node=$(find_covering_node "$file")
    if [ -n "$node" ]; then
        if [ -z "${NODE_FILES[$node]:-}" ]; then
            NODE_FILES[$node]="$file"
            NODE_CONTENT[$node]=$(cat "$node" 2>/dev/null || echo "")
        else
            NODE_FILES[$node]="${NODE_FILES[$node]}"$'\n'"$file"
        fi
    fi
done <<< "$CHANGED_FILES"

AFFECTED_NODE_COUNT=${#NODE_FILES[@]}
echo "Affected Intent Nodes: $AFFECTED_NODE_COUNT"
```

**Step 2: Test node discovery**

Run: `./intent-layer/scripts/review_pr.sh HEAD~3 HEAD`
Expected: Shows affected node count

**Step 3: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add Intent Node discovery and file mapping"
```

---

## Task 4: Add Risk Scoring

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add risk scoring function**

Add after node discovery:

```bash
# Semantic signal patterns
SECURITY_PATTERNS="auth|password|token|secret|permission|encrypt|credential|login|session"
DATA_PATTERNS="migration|schema|DELETE|DROP|transaction|database|sql|query"
API_PATTERNS="/api/|endpoint|route|breaking|deprecated|version"

# Calculate risk score
calculate_risk_score() {
    local score=0
    local factors=""

    # Files changed: 1 point per 5 files
    local file_points=$((FILE_COUNT / 5))
    if [ $file_points -gt 0 ]; then
        score=$((score + file_points))
        factors="${factors}Files changed: +${file_points}\n"
    fi

    # Count contracts and pitfalls in affected nodes
    local contract_count=0
    local pitfall_count=0
    local critical_count=0

    for node in "${!NODE_CONTENT[@]}"; do
        local content="${NODE_CONTENT[$node]}"

        # Count items in Contracts section
        local in_contracts=$(echo "$content" | grep -c -iE "^- .*(must|never|always|require)" || echo "0")
        contract_count=$((contract_count + in_contracts))

        # Count items in Pitfalls section
        local in_pitfalls=$(echo "$content" | grep -c -iE "^- .*(pitfall|silently|unexpected|surprising)" || echo "0")
        pitfall_count=$((pitfall_count + in_pitfalls))

        # Count critical items
        local critical=$(echo "$content" | grep -c -E "^- (⚠️|CRITICAL:)" || echo "0")
        critical_count=$((critical_count + critical))
    done

    # Contracts: 2 points each
    if [ $contract_count -gt 0 ]; then
        local contract_points=$((contract_count * 2))
        score=$((score + contract_points))
        factors="${factors}Contracts ($contract_count): +${contract_points}\n"
    fi

    # Pitfalls: 3 points each
    if [ $pitfall_count -gt 0 ]; then
        local pitfall_points=$((pitfall_count * 3))
        score=$((score + pitfall_points))
        factors="${factors}Pitfalls ($pitfall_count): +${pitfall_points}\n"
    fi

    # Critical items: 5 points each
    if [ $critical_count -gt 0 ]; then
        local critical_points=$((critical_count * 5))
        score=$((score + critical_points))
        factors="${factors}Critical items ($critical_count): +${critical_points}\n"
    fi

    # Semantic signals in changed files
    local diff_content=$(git diff "$BASE_REF" "$HEAD_REF" 2>/dev/null || echo "")

    if echo "$diff_content" | grep -qiE "$SECURITY_PATTERNS"; then
        score=$((score + 10))
        factors="${factors}Security patterns: +10\n"
    fi

    if echo "$diff_content" | grep -qiE "$DATA_PATTERNS"; then
        score=$((score + 10))
        factors="${factors}Data patterns: +10\n"
    fi

    if echo "$diff_content" | grep -qiE "$API_PATTERNS"; then
        score=$((score + 5))
        factors="${factors}API patterns: +5\n"
    fi

    # Output
    RISK_SCORE=$score
    RISK_FACTORS="$factors"

    if [ $score -le 15 ]; then
        RISK_LEVEL="Low"
    elif [ $score -le 35 ]; then
        RISK_LEVEL="Medium"
    else
        RISK_LEVEL="High"
    fi
}

calculate_risk_score
```

**Step 2: Test risk calculation**

Run: `./intent-layer/scripts/review_pr.sh HEAD~3 HEAD`
Expected: No errors, script completes

**Step 3: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add risk scoring with quantitative and semantic factors"
```

---

## Task 5: Add Checklist Generation

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add checklist extraction function**

Add after risk scoring:

```bash
# Extract checklist items from nodes
generate_checklist() {
    CRITICAL_ITEMS=""
    RELEVANT_ITEMS=""
    PITFALL_ITEMS=""

    for node in "${!NODE_CONTENT[@]}"; do
        local content="${NODE_CONTENT[$node]}"
        local files="${NODE_FILES[$node]}"

        # Extract critical items (always include)
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            CRITICAL_ITEMS="${CRITICAL_ITEMS}- [ ] ${line} (${node})\n"
        done < <(echo "$content" | grep -E "^- (⚠️|CRITICAL:)" | sed 's/^- //' || true)

        # Extract contracts that match changed file keywords
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            # Check if any changed file keyword appears in the contract
            local is_relevant=false
            while IFS= read -r file; do
                [ -z "$file" ] && continue
                local filename=$(basename "$file" | sed 's/\.[^.]*$//')
                if echo "$line" | grep -qi "$filename"; then
                    is_relevant=true
                    RELEVANT_ITEMS="${RELEVANT_ITEMS}- [ ] ${line} (${node})\n      Changed: ${file}\n"
                    break
                fi
            done <<< "$files"
        done < <(echo "$content" | grep -E "^- .*(must|never|always|require)" | grep -vE "^- (⚠️|CRITICAL:)" | sed 's/^- //' || true)

        # Extract pitfalls
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            PITFALL_ITEMS="${PITFALL_ITEMS}- [ ] ${line} (${node})\n"
        done < <(echo "$content" | grep -iE "^- .*(pitfall|silently|unexpected|surprising)" | sed 's/^- //' || true)
    done
}

generate_checklist
```

**Step 2: Test checklist generation**

Run: `./intent-layer/scripts/review_pr.sh HEAD~3 HEAD`
Expected: No errors

**Step 3: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add checklist generation from Intent Nodes"
```

---

## Task 6: Add AI-Generated Code Checks

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add AI-specific detection functions**

Add after checklist generation:

```bash
# AI-generated code specific checks
run_ai_checks() {
    [ "$AI_GENERATED" = false ] && return

    AI_DRIFT_WARNINGS=""
    AI_OVERENGINEERING=""
    AI_PATTERN_ISSUES=""
    AI_PITFALL_ALERTS=""

    local diff_content=$(git diff "$BASE_REF" "$HEAD_REF" 2>/dev/null || echo "")

    # Over-engineering detection
    # New files in utils/helpers/common
    local new_files=$(git diff --name-only --diff-filter=A "$BASE_REF" "$HEAD_REF" 2>/dev/null || echo "")
    while IFS= read -r file; do
        [ -z "$file" ] && continue
        if [[ "$file" == *"/utils/"* ]] || [[ "$file" == *"/helpers/"* ]] || [[ "$file" == *"/common/"* ]]; then
            AI_OVERENGINEERING="${AI_OVERENGINEERING}- New abstraction: ${file}\n  Is this necessary or could existing patterns handle it?\n"
        fi
    done <<< "$new_files"

    # Excessive try/catch (more than 3 new try blocks)
    local try_count=$(echo "$diff_content" | grep -c "^+.*try {" || echo "0")
    if [ "$try_count" -gt 3 ]; then
        AI_OVERENGINEERING="${AI_OVERENGINEERING}- Excessive error handling: ${try_count} new try/catch blocks\n  Check if all error handling adds value\n"
    fi

    # New interfaces with single implementation pattern
    local new_interfaces=$(echo "$diff_content" | grep -c "^+.*interface " || echo "0")
    if [ "$new_interfaces" -gt 2 ]; then
        AI_OVERENGINEERING="${AI_OVERENGINEERING}- Multiple new interfaces: ${new_interfaces}\n  Verify these aren't premature abstractions\n"
    fi

    # Pitfall proximity - check if changes touch files near documented pitfalls
    for node in "${!NODE_CONTENT[@]}"; do
        local content="${NODE_CONTENT[$node]}"
        local files="${NODE_FILES[$node]}"
        local node_dir=$(dirname "$node")

        # Extract pitfalls
        while IFS= read -r pitfall; do
            [ -z "$pitfall" ] && continue
            AI_PITFALL_ALERTS="${AI_PITFALL_ALERTS}- ${node_dir}: ${pitfall}\n  Verify: Does new code handle this edge case?\n"
        done < <(echo "$content" | grep -iE "^- .*(silently|fails|unexpected)" | sed 's/^- //' | head -3 || true)
    done
}

run_ai_checks
```

**Step 2: Test AI checks**

Run: `./intent-layer/scripts/review_pr.sh HEAD~3 HEAD --ai-generated`
Expected: No errors

**Step 3: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add AI-generated code detection checks"
```

---

## Task 7: Add Output Formatting

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add output generation function**

Add after AI checks:

```bash
# Generate output
generate_output() {
    local output=""

    # Layer 1: Risk Summary
    output+="# PR Review Summary\n\n"
    output+="## Risk Assessment\n\n"
    output+="**Score: ${RISK_SCORE} (${RISK_LEVEL})**\n\n"
    output+="Contributing factors:\n"
    output+="${RISK_FACTORS}\n"

    case $RISK_LEVEL in
        "Low")
            output+="Recommendation: Standard review\n\n"
            ;;
        "Medium")
            output+="Recommendation: Careful review recommended\n\n"
            ;;
        "High")
            output+="Recommendation: Thorough review required\n\n"
            ;;
    esac

    [ "$OUTPUT_MODE" = "summary" ] && { echo -e "$output"; return; }

    # Layer 2: Checklist
    output+="---\n\n"
    output+="## Review Checklist\n\n"

    if [ -n "$CRITICAL_ITEMS" ]; then
        output+="### Critical (always verify)\n\n"
        output+="${CRITICAL_ITEMS}\n"
    fi

    if [ -n "$RELEVANT_ITEMS" ]; then
        output+="### Relevant to this PR\n\n"
        output+="${RELEVANT_ITEMS}\n"
    fi

    if [ -n "$PITFALL_ITEMS" ]; then
        output+="### Pitfalls in affected areas\n\n"
        output+="${PITFALL_ITEMS}\n"
    fi

    # AI-specific sections
    if [ "$AI_GENERATED" = true ]; then
        output+="---\n\n"
        output+="## AI-Generated Code Checks\n\n"

        if [ -n "$AI_OVERENGINEERING" ]; then
            output+="### Complexity Check\n\n"
            output+="Potential over-engineering detected:\n\n"
            output+="${AI_OVERENGINEERING}\n"
        fi

        if [ -n "$AI_PITFALL_ALERTS" ]; then
            output+="### Pitfall Proximity Alerts\n\n"
            output+="AI modified code adjacent to known sharp edges:\n\n"
            output+="${AI_PITFALL_ALERTS}\n"
        fi
    fi

    [ "$OUTPUT_MODE" = "checklist" ] && { echo -e "$output"; return; }

    # Layer 3: Detailed Context
    output+="---\n\n"
    output+="## Detailed Context\n\n"

    for node in "${!NODE_FILES[@]}"; do
        local files="${NODE_FILES[$node]}"
        local file_count=$(echo "$files" | grep -v '^$' | wc -l | tr -d ' ')

        output+="### ${node}\n\n"
        output+="**Covers:** ${file_count} changed files\n\n"

        # Show relevant sections from node
        local content="${NODE_CONTENT[$node]}"

        # Extract Contracts section
        local contracts=$(echo "$content" | sed -n '/## Contracts/,/^## /p' | head -20 || echo "")
        if [ -n "$contracts" ]; then
            output+="#### Contracts\n\n"
            output+="${contracts}\n\n"
        fi

        # Extract Pitfalls section
        local pitfalls=$(echo "$content" | sed -n '/## Pitfalls/,/^## /p' | head -20 || echo "")
        if [ -n "$pitfalls" ]; then
            output+="#### Pitfalls\n\n"
            output+="${pitfalls}\n\n"
        fi

        output+="---\n\n"
    done

    echo -e "$output"
}

# Output
if [ -n "$OUTPUT_FILE" ]; then
    generate_output > "$OUTPUT_FILE"
    echo "Output written to: $OUTPUT_FILE"
else
    generate_output
fi

# Exit code mode
if [ "$EXIT_CODE_MODE" = true ]; then
    case $RISK_LEVEL in
        "Low") exit 0 ;;
        "Medium") exit 1 ;;
        "High") exit 2 ;;
    esac
fi
```

**Step 2: Test full output**

Run: `./intent-layer/scripts/review_pr.sh HEAD~3 HEAD --full`
Expected: Formatted markdown output

**Step 3: Test exit code mode**

Run: `./intent-layer/scripts/review_pr.sh HEAD~3 HEAD --exit-code; echo "Exit: $?"`
Expected: Shows exit code 0, 1, or 2

**Step 4: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add output formatting with progressive disclosure layers"
```

---

## Task 8: Add GitHub PR Integration

**Files:**
- Modify: `intent-layer/scripts/review_pr.sh`

**Step 1: Add PR metadata fetching**

Add after argument parsing, before git validation:

```bash
# Fetch PR metadata if --pr flag used
PR_TITLE=""
PR_BODY=""
PR_AUTHOR=""

if [ -n "$PR_NUMBER" ]; then
    if ! command -v gh &> /dev/null; then
        echo "Warning: gh CLI not found, skipping PR metadata" >&2
    else
        PR_TITLE=$(gh pr view "$PR_NUMBER" --json title -q '.title' 2>/dev/null || echo "")
        PR_BODY=$(gh pr view "$PR_NUMBER" --json body -q '.body' 2>/dev/null || echo "")
        PR_AUTHOR=$(gh pr view "$PR_NUMBER" --json author -q '.author.login' 2>/dev/null || echo "")

        if [ -n "$PR_TITLE" ]; then
            echo "PR #${PR_NUMBER}: ${PR_TITLE}"
            echo "Author: ${PR_AUTHOR}"
        fi
    fi
fi
```

**Step 2: Add intent drift detection for AI mode**

Add to `run_ai_checks` function:

```bash
    # Intent drift detection (when PR metadata available)
    if [ -n "$PR_TITLE" ] || [ -n "$PR_BODY" ]; then
        local pr_text="${PR_TITLE} ${PR_BODY}"

        for node in "${!NODE_CONTENT[@]}"; do
            local content="${NODE_CONTENT[$node]}"

            # Check for conflicting approaches
            # JWT vs session tokens
            if echo "$pr_text" | grep -qi "jwt" && echo "$content" | grep -qi "session.*not.*jwt\|no.*jwt"; then
                AI_DRIFT_WARNINGS="${AI_DRIFT_WARNINGS}- PR mentions JWT but ${node} says: avoid JWT\n"
            fi

            # Check architecture decisions
            while IFS= read -r decision; do
                [ -z "$decision" ] && continue
                # Extract the "don't do X" patterns
                local avoid=$(echo "$decision" | grep -oiE "not|avoid|never|don't" || echo "")
                if [ -n "$avoid" ]; then
                    local pattern=$(echo "$decision" | grep -oiE "[a-zA-Z]+" | head -3 | tr '\n' '|' | sed 's/|$//')
                    if echo "$pr_text" | grep -qiE "$pattern"; then
                        AI_DRIFT_WARNINGS="${AI_DRIFT_WARNINGS}- Potential conflict: PR may contradict: ${decision}\n"
                    fi
                fi
            done < <(echo "$content" | grep -iE "^- .*(architecture|decision|approach)" | head -5 || true)
        done
    fi
```

**Step 3: Update output to include drift warnings**

Add to `generate_output` in the AI section:

```bash
        if [ -n "$AI_DRIFT_WARNINGS" ]; then
            output+="### Intent Drift Warnings\n\n"
            output+="${AI_DRIFT_WARNINGS}\n"
        fi
```

**Step 4: Test with a real PR (if available)**

Run: `./intent-layer/scripts/review_pr.sh main HEAD --pr 1 --ai-generated` (adjust PR number)
Expected: Shows PR metadata if gh CLI available

**Step 5: Commit**

```bash
git add intent-layer/scripts/review_pr.sh
git commit -m "feat: add GitHub PR integration with intent drift detection"
```

---

## Task 9: Create pr-review SKILL.md

**Files:**
- Create: `intent-layer/pr-review/SKILL.md`

**Step 1: Create the skill directory and file**

```bash
mkdir -p intent-layer/pr-review
```

**Step 2: Write the skill content**

```markdown
---
name: pr-review
description: >
  Review PRs against the Intent Layer. Use for reviewing AI-generated PRs
  or having AI review human PRs. Provides risk scoring, checklists, and
  contract verification.
argument-hint: "[BASE_REF] [HEAD_REF] [--pr NUMBER] [--ai-generated]"
---

# PR Review

Review a PR against the Intent Layer for contract compliance, pitfall awareness, and risk assessment.

## Quick Start

```bash
# Basic review
scripts/review_pr.sh main HEAD

# Review AI-generated PR
scripts/review_pr.sh main HEAD --ai-generated

# Review with GitHub PR context
scripts/review_pr.sh main HEAD --pr 123 --ai-generated
```

## Interactive Review Workflow

### Step 1: Run Initial Analysis

```bash
scripts/review_pr.sh main HEAD --ai-generated
```

Review the output:
1. **Risk Score** - Is this Low/Medium/High?
2. **Critical Items** - These MUST be verified
3. **AI Checks** - Any drift or over-engineering warnings?

### Step 2: Walk Through Critical Items

For each critical item in the checklist:
1. Read the contract/invariant
2. Find the relevant code in the diff
3. Verify the code respects the constraint
4. Mark checked: `- [x]` or flag concern

### Step 3: Check AI-Specific Warnings

If `--ai-generated` was used:

**Over-engineering flags:**
- New abstractions: Are they necessary?
- Excessive try/catch: Does error handling add value?
- New interfaces: Premature abstraction?

**Pitfall proximity:**
- For each alert, verify the AI handled the edge case
- If not, flag for fix before merge

**Intent drift:**
- If PR approach conflicts with documented architecture, escalate

### Step 4: Surface Findings

Use the agent-feedback-protocol format for any discoveries:

```markdown
### Intent Layer Feedback

| Type | Location | Finding |
|------|----------|---------|
| Missing pitfall | `src/api/AGENTS.md` | [description] |
| Stale contract | `CLAUDE.md` | [description] |
```

### Step 5: Generate Review Summary

Output a structured review comment:

```markdown
## PR Review Summary

**Risk: [Score] ([Level])**

### Verified
- [x] Auth tokens validated before DB write
- [x] Rate limiting uses Redis

### Concerns
- [ ] New abstraction in `utils/helper.ts` may be unnecessary

### Intent Layer Feedback
[Any findings to update nodes]
```

## CI Integration

```yaml
- name: PR Review Check
  run: |
    ./intent-layer/scripts/review_pr.sh origin/main HEAD --exit-code --ai-generated
  # Exit 0 = low risk, 1 = medium, 2 = high
```

## Output Modes

| Flag | Output |
|------|--------|
| `--summary` | Risk score only |
| `--checklist` | Score + checklist |
| `--full` | All layers (default) |

## When to Use

- **Before merging AI-generated PRs** - Verify contracts respected
- **AI reviewing human PRs** - Systematic contract checking
- **CI gate** - Block high-risk PRs for manual review

## Related

- `detect_changes.sh` - Foundation for affected node discovery
- `agent-feedback-protocol.md` - Format for surfacing findings
- `validate_node.sh` - Validate node updates after review
```

**Step 3: Commit**

```bash
git add intent-layer/pr-review/SKILL.md
git commit -m "feat: add pr-review skill for interactive PR review"
```

---

## Task 10: Create Example Output Reference

**Files:**
- Create: `intent-layer/references/pr-review-output.md`

**Step 1: Write example output**

```markdown
# PR Review Output Examples

Example outputs from `review_pr.sh` for reference.

## Low Risk Example

```markdown
# PR Review Summary

## Risk Assessment

**Score: 8 (Low)**

Contributing factors:
Files changed: +2
Contracts (2): +4
API patterns: +5

Recommendation: Standard review

---

## Review Checklist

### Relevant to this PR

- [ ] API responses must include X-Request-ID header (src/api/AGENTS.md)
      Changed: src/api/routes/users.ts

### Pitfalls in affected areas

- [ ] Rate limiter fails silently when Redis unavailable (src/api/AGENTS.md)
```

## High Risk AI-Generated Example

```markdown
# PR Review Summary

## Risk Assessment

**Score: 47 (High)**

Contributing factors:
Files changed: +3
Contracts (5): +10
Pitfalls (4): +12
Critical items (2): +10
Security patterns: +10
Data patterns: +10

Recommendation: Thorough review required

---

## Review Checklist

### Critical (always verify)

- [ ] ⚠️ Auth tokens must be validated before any database write (src/auth/AGENTS.md)
- [ ] CRITICAL: Never cache user permissions (src/api/AGENTS.md)

### Relevant to this PR

- [ ] All database writes require explicit transaction (src/db/AGENTS.md)
      Changed: src/db/repositories/user.ts

### Pitfalls in affected areas

- [ ] Migration rollback requires specific flag order (src/db/AGENTS.md)
- [ ] `config/legacy.json` looks unused but controls feature flags (CLAUDE.md)

---

## AI-Generated Code Checks

### Intent Drift Warnings

- Potential conflict: PR mentions JWT but src/auth/AGENTS.md says: use session tokens, NOT JWT

### Complexity Check

Potential over-engineering detected:

- New abstraction: src/utils/authHelper.ts
  Is this necessary or could existing patterns handle it?

- Excessive error handling: 5 new try/catch blocks
  Check if all error handling adds value

### Pitfall Proximity Alerts

AI modified code adjacent to known sharp edges:

- src/auth: Rate limiter fails silently when Redis unavailable
  Verify: Does new code handle this edge case?

- src/db: Migration scripts assume PostgreSQL 14+
  Verify: Does new code maintain compatibility?

---

## Detailed Context

### src/auth/AGENTS.md

**Covers:** 3 changed files

#### Contracts

- ⚠️ Auth tokens must be validated before any database write
- Session tokens expire after 1 hour
- Use bcrypt for password hashing (cost factor 12)

#### Pitfalls

- Rate limiter fails silently when Redis unavailable
- Token refresh window is 5 minutes before expiry

---

### src/db/AGENTS.md

**Covers:** 2 changed files

#### Contracts

- All writes require explicit transaction
- Migrations must be reversible
- CRITICAL: Never cache user permissions

#### Pitfalls

- Migration rollback requires `--lock-timeout=5000` flag
- Connection pool exhaustion at >100 concurrent queries
```

## CI Exit Codes

| Risk Level | Exit Code |
|------------|-----------|
| Low (0-15) | 0 |
| Medium (16-35) | 1 |
| High (36+) | 2 |
```

**Step 2: Commit**

```bash
git add intent-layer/references/pr-review-output.md
git commit -m "docs: add PR review output examples"
```

---

## Task 11: Update Documentation

**Files:**
- Modify: `intent-layer/SKILL.md`
- Modify: `CLAUDE.md`

**Step 1: Add pr-review to intent-layer SKILL.md Resources table**

Find the Scripts table in `intent-layer/SKILL.md` and add:

```markdown
| `review_pr.sh` | Review PR against Intent Layer |
```

**Step 2: Add review_pr.sh to root CLAUDE.md**

Find the Scripts table in `CLAUDE.md` and add:

```markdown
| `review_pr.sh` | Review PR against Intent Layer contracts |
```

**Step 3: Commit**

```bash
git add intent-layer/SKILL.md CLAUDE.md
git commit -m "docs: add review_pr.sh to documentation"
```

---

## Task 12: Final Integration Test

**Step 1: Run full review on recent commits**

```bash
./intent-layer/scripts/review_pr.sh HEAD~5 HEAD --ai-generated --full
```

Expected: Complete output with all sections

**Step 2: Test exit code mode**

```bash
./intent-layer/scripts/review_pr.sh HEAD~5 HEAD --exit-code
echo "Exit code: $?"
```

Expected: Exit code 0, 1, or 2

**Step 3: Test output to file**

```bash
./intent-layer/scripts/review_pr.sh HEAD~5 HEAD --output /tmp/review.md
cat /tmp/review.md
```

Expected: Output written to file

**Step 4: Validate script with help**

```bash
./intent-layer/scripts/review_pr.sh --help
```

Expected: Help message displays

**Step 5: Final commit if any fixes needed**

```bash
git status
# If changes needed, fix and commit
```
