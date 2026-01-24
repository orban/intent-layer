# Learning Layer Enhancements Design

**Date:** 2026-01-23
**Status:** Approved

## Overview

Two targeted enhancements to improve Intent Layer adoption and coverage:

1. **New Directory Detection** - Notify when files are written to new directories that may benefit from AGENTS.md coverage
2. **Enhanced SessionStart Prompt** - Stronger language when no Intent Layer exists

## Design Decisions

### Feature 1: New Directory Detection

**Trigger:** PostToolUse hook on Write tool (existing `post-edit-check.sh`)

**Detection Logic:**
```
IF file was written to a directory that:
  - Has no AGENTS.md (not already covered at this level)
  - Has ≤2 files (newly created, not established)
  - Is NOT in exclusion list (node_modules, .git, build, dist, __pycache__, etc.)
  - Is NOT a dotfile directory (.github, .vscode)
  - Parent directory DOES have an AGENTS.md or CLAUDE.md (extending hierarchy)
THEN
  Output notification
```

**Output:**
```
📁 New directory `src/utils/` created - may need AGENTS.md coverage as it grows.
   Run `/intent-layer-maintenance` when ready to extend the hierarchy.
```

**Silent for:**
- Writes to existing directories with many files
- Writes to temp/build/dependency directories
- Projects without any Intent Layer (handled by SessionStart)

### Feature 2: Enhanced SessionStart Language

**Before (soft):**
```
## Intent Layer: Not Configured

This project doesn't have an Intent Layer yet...

**Consider running `/intent-layer` to:**
...
This is optional but helps...
```

**After (stronger):**
```
## ⚠️ Intent Layer: Not Configured

No CLAUDE.md or AGENTS.md found in this project.

**Run `/intent-layer` to set up AI-friendly navigation:**
- Contracts, patterns, and pitfalls that prevent mistakes
- Automatic learning loop captures gotchas as you work
- Compression ratio ~100:1 vs reading raw code

Without this, I'm navigating blind. Setup takes ~5 minutes for most projects.
```

## Implementation

**Files to modify:**
- `scripts/post-edit-check.sh` - Add new directory detection (~20 lines)
- `scripts/inject-learnings.sh` - Update SessionStart message (~5 lines)
- `tests/test_hooks.sh` - Add tests for new behavior

**No new files, hooks, or dependencies.**

## Testing

1. Write a file to a new directory in a project with Intent Layer → should see notification
2. Write a file to node_modules or .git → should be silent
3. Write a file to established directory (10+ files) → should be silent
4. SessionStart in project without Intent Layer → should see enhanced message
