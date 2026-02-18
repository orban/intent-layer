# lib/prompt_builder.py
from __future__ import annotations


FLAT_PREAMBLE = """Before making changes, read the CLAUDE.md file at the project root to understand:
- Project structure and key patterns
- How to run tests

"""

INTENT_LAYER_PREAMBLE = """Before making changes:
1. Read the CLAUDE.md file at the project root for project context, architecture, and a Downlinks table
2. Check the Downlinks table — it lists AGENTS.md files in subdirectories with focused context for each subsystem
3. Read the AGENTS.md file(s) most relevant to the area of code you need to fix
4. Pay attention to Pitfalls and Contracts sections — they document non-obvious gotchas

"""


def build_prompt_from_commit_message(message: str, preamble: str | None = None) -> str:
    """Build a prompt from a git commit message."""
    preamble_text = preamble if preamble else ""
    return f"""{preamble_text}Fix the following bug:

{message}

The fix should make the existing tests pass."""


def build_prompt_from_failing_test(test_output: str, preamble: str | None = None) -> str:
    """Build a prompt from failing test output."""
    preamble_text = preamble if preamble else ""
    return f"""{preamble_text}The following test is failing:

```
{test_output}
```

Find and fix the bug that causes this test to fail. Do not modify the test itself."""


def build_prompt_from_issue(title: str, body: str, preamble: str | None = None) -> str:
    """Build a prompt from a GitHub issue."""
    preamble_text = preamble if preamble else ""
    return f"""{preamble_text}Fix the following bug:

**{title}**

{body}

The fix should make the existing tests pass."""


def build_flat_generation_prompt() -> str:
    """Generate a single CLAUDE.md overview file.

    EXACT prompt from the AGENTbench paper's init_planner.py:60-80.
    Copied verbatim for experimental faithfulness.
    """
    return '''Please analyze this codebase and create a CLAUDE.md file, which will be given to future instances of Claude Code to operate in this repository.

What to add:
1. Commands that will be commonly used, such as how to build, lint, and run tests. Include the necessary commands to develop in this codebase, such as how to run a single test.
2. High-level code architecture and structure so that future instances can be productive more quickly. Focus on the "big picture" architecture that requires reading multiple files to understand.

Usage notes:
- If there's already a CLAUDE.md, suggest improvements to it.
- When you make the initial CLAUDE.md, do not repeat yourself and do not include obvious instructions like "Provide helpful error messages to users", "Write unit tests for all new utilities", "Never include sensitive information (API keys, tokens) in code or commits".
- Avoid listing every component or file structure that can be easily discovered.
- Don't include generic development practices.
- If there are Cursor rules (in .cursor/rules/ or .cursorrules) or Copilot rules (in .github/copilot-instructions.md), make sure to include the important parts.
- If there is a README.md, make sure to include the important parts.
- Do not make up information such as "Common Development Tasks", "Tips for Development", "Support and Documentation" unless this is expressly included in other files that you read.
- Be sure to prefix the file with the following text:

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.'''


def build_skill_generation_prompt(plugin_root: str) -> str:
    """Build prompt for Intent Layer generation using the actual plugin.

    Mirrors what happens when a user invokes /intent-layer:
    CLAUDE_PLUGIN_ROOT is set in the env (by the caller), and the prompt
    gives Claude the same workflow from the skill.
    """
    scripts = f"{plugin_root}/scripts"
    return f"""Create an Intent Layer for this codebase to help future agents fix bugs.

IMPORTANT: Your current working directory is the TARGET repository to analyze.
All commands below use "." (current directory) as the target. Do NOT pass any
other path — the scripts at {scripts}/ are tools, not the target.

## Step 0: Detect State

Run: {scripts}/detect_state.sh .

If this reports "complete", the Intent Layer already exists. In that case, skip
to Step 5 (validate). Otherwise continue.

## Step 1: Measure

Run: {scripts}/estimate_all_candidates.sh .
This shows which directories are large enough to warrant their own AGENTS.md.

## Step 2: Mine Git History

Run: {scripts}/mine_git_history.sh .
This extracts pitfalls, anti-patterns, and contracts from past bug fixes and reverts.
Git-mined pitfalls are the highest-value content in any node.

## Step 3: Create Root CLAUDE.md

Create a CLAUDE.md in the current directory (the project root) with these sections:
- **TL;DR**: One-line project description
- **Entry Points**: Table of common tasks and where to start
- **Architecture**: Components, data flow, key patterns (big picture only)
- **Contracts**: Non-type-enforced invariants that must hold
- **Pitfalls**: What looks wrong but is correct, what looks correct but breaks
  (include findings from git history mining)
- **Downlinks**: Table linking to child AGENTS.md nodes

Rules:
- Keep under 4000 tokens (target 100:1 compression ratio)
- Don't list every file — focus on non-obvious locations
- Don't include generic dev practices
- Include how to build, test, and run the project

## Step 4: Create Child AGENTS.md Nodes

For each directory that has >20k tokens OR a distinct responsibility, create an AGENTS.md with:
- Purpose and design rationale
- Code map (non-obvious file locations)
- Key exports used by other modules
- Contracts specific to this area
- Pitfalls specific to this area (include git history findings)

Rules:
- Each node under 4000 tokens
- Don't create nodes for simple utilities or config-only dirs
- Child nodes are named AGENTS.md (not CLAUDE.md)

## Step 5: Validate

Run: {scripts}/validate_node.sh CLAUDE.md
Run validation on each child AGENTS.md too.

Focus on information that would help someone unfamiliar with the codebase navigate and fix bugs safely."""
