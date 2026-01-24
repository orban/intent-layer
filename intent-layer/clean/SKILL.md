---
name: clean
description: >
  Remove the Intent Layer from a repository. Deletes all child AGENTS.md files
  and removes the Intent Layer section from the root CLAUDE.md.
---

# Intent Layer Clean

Remove the Intent Layer infrastructure from a repository completely.

## When to Use

- Removing Intent Layer from a project entirely
- Starting fresh after Intent Layer has drifted beyond repair
- Cleaning up before a major architectural overhaul
- Removing experimental Intent Layer setup

## Process

### 1. Find All Intent Layer Files

```bash
# Find child AGENTS.md files (excluding root)
find . -name "AGENTS.md" -not -path "./AGENTS.md" -type f 2>/dev/null

# Check for root AGENTS.md symlink
ls -la ./AGENTS.md 2>/dev/null
```

### 2. Detect Intent Layer Section in Root

Check if CLAUDE.md has an Intent Layer section:

```bash
grep -n "^## Intent Layer" ./CLAUDE.md 2>/dev/null
```

### 3. Show What Will Be Changed

Present the full scope to the user:

```markdown
## Intent Layer Removal Plan

### Files to Delete
| Path | Size |
|------|------|
| src/api/AGENTS.md | 2.1k |
| src/core/AGENTS.md | 1.8k |
| ./AGENTS.md (symlink) | - |

### Root CLAUDE.md Changes
- Remove "## Intent Layer" section (lines 45-89)

**Preserved:** ./CLAUDE.md (without Intent Layer section)

Total: 3 files deleted, 1 section removed
```

### 4. Confirm with User

Ask: "Remove Intent Layer completely? This will delete X files and remove the Intent Layer section from CLAUDE.md."

- If user confirms: proceed
- If user declines: abort

### 5. Execute Removal

#### Delete Child AGENTS.md Files

```bash
rm [path/to/AGENTS.md]
```

#### Remove Root AGENTS.md Symlink (if exists)

```bash
rm ./AGENTS.md  # Only if it's a symlink to CLAUDE.md
```

#### Remove Intent Layer Section from CLAUDE.md

Remove the `## Intent Layer` section and everything until the next `## ` heading (or end of file).

Pattern to match and remove:
- Starts with `## Intent Layer` (with optional text after)
- Ends at next `## ` heading or EOF
- Include any blank lines before the next section

### 6. Report Results

```markdown
## Intent Layer Removed

### Deleted Files
- src/api/AGENTS.md
- src/core/AGENTS.md
- ./AGENTS.md (symlink)

### Modified Files
- ./CLAUDE.md (Intent Layer section removed)

To restore Intent Layer: /intent-layer
```

## Safety

- **Root CLAUDE.md preserved** - Only the Intent Layer section is removed, other content stays
- **Requires confirmation** - Shows full plan before any changes
- **Section detection** - Only removes if `## Intent Layer` heading exists
- **Symlink-aware** - Only removes root AGENTS.md if it's a symlink

## What Happens

| Item | Action |
|------|--------|
| `./CLAUDE.md` | Intent Layer section removed |
| `./AGENTS.md` | Deleted if symlink to CLAUDE.md |
| `src/*/AGENTS.md` | Deleted |
| Other CLAUDE.md content | Preserved |

## Edge Cases

### No Intent Layer Section in CLAUDE.md
If the root has no `## Intent Layer` section, skip that step and only delete AGENTS.md files.

### No Child AGENTS.md Files
If no child files exist, only remove the section from CLAUDE.md.

### AGENTS.md is Not a Symlink
If root AGENTS.md is a real file (not symlink), warn user and ask whether to delete it.

## Output

Confirmation of all deleted files and modified sections, with reminder of how to restore.
