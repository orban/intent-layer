# Intent Layer Generation Improvement

**Date**: 2026-01-22
**Status**: Approved
**Goal**: Higher quality AGENTS.md generation + realistic evaluation workflow

## Context

The eval-harness tests whether having an Intent Layer helps Claude fix bugs. The current implementation uses a minimal prompt for generation and doesn't explicitly tell Claude to use the generated AGENTS.md files.

## Design Decisions

1. **Scenario**: On-demand generation (developer creates Intent Layer before bug fixing)
2. **Coverage**: Comprehensive - entry points, pitfalls, architecture, contracts
3. **Depth**: Hierarchical - root CLAUDE.md + child AGENTS.md nodes
4. **Usage**: Explicit instruction to read AGENTS.md before fixing

## Changes

### 1. Improved Generation Prompt

**File**: `lib/task_runner.py` (lines 72-76)

```python
SKILL_GENERATION_PROMPT = """Create an Intent Layer for this codebase to help with bug fixing.

1. Run scripts/detect_state.sh to check current state
2. Run scripts/analyze_structure.sh to find semantic boundaries
3. Create a root CLAUDE.md with:
   - Entry points for key functionality
   - Architecture overview (components, data flow)
   - Pitfalls extracted from git history (use git-history sub-skill)
   - Contracts that must be maintained
4. Create AGENTS.md child nodes for directories with distinct responsibilities

Focus on information that would help someone unfamiliar with the codebase navigate and fix bugs safely."""
```

### 2. Improved Bug Fix Prompts

**File**: `lib/prompt_builder.py`

All prompt builders prepend:

```
Before making changes, read the AGENTS.md files (starting with CLAUDE.md at the root) to understand:
- Where relevant code is located
- What pitfalls to avoid
- What contracts must be maintained
```

### 3. Enhanced Metrics

**File**: `lib/task_runner.py`

```python
@dataclass
class SkillGenerationMetrics:
    wall_clock_seconds: float
    input_tokens: int
    output_tokens: int
    files_created: list[str]  # Which AGENTS.md files were created

@dataclass
class TaskResult:
    # ... existing fields ...
    agents_files_read: list[str] | None = None  # Which AGENTS.md Claude read during fix
```

### 4. Claude Output Parsing

**File**: `lib/claude_runner.py`

Add helper to extract Read tool calls from JSON output to populate `agents_files_read`.

## Files Changed

| File | Change |
|------|--------|
| `lib/task_runner.py` | Generation prompt, metrics fields, AGENTS.md tracking |
| `lib/prompt_builder.py` | All prompt builders reference AGENTS.md |
| `lib/claude_runner.py` | Add Read tool call extraction |
| `tests/test_prompt_builder.py` | Update expected prompts |
| `tests/test_task_runner.py` | Test new metrics fields |

## Not Changing

- `lib/reporter.py` - New fields appear in JSON automatically
- `lib/cli.py` - No CLI changes
- Task YAML format - No schema changes
