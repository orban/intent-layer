# lib/prompt_builder.py
from __future__ import annotations


FLAT_PREAMBLE = """Before making changes, read the CLAUDE.md file at the project root to understand:
- Project structure and key patterns
- How to run tests

"""

INTENT_LAYER_PREAMBLE = """Before making changes, read the AGENTS.md files (starting with CLAUDE.md at the root) to understand:
- Where relevant code is located
- What pitfalls to avoid
- What contracts must be maintained

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


def build_skill_generation_prompt() -> str:
    """Build prompt for Intent Layer generation."""
    return """Create an Intent Layer for this codebase to help with bug fixing.

1. Run scripts/detect_state.sh to check current state
2. Run scripts/analyze_structure.sh to find semantic boundaries
3. Create a root CLAUDE.md with:
   - Entry points for key functionality
   - Architecture overview (components, data flow)
   - Pitfalls extracted from git history (use git-history sub-skill)
   - Contracts that must be maintained
4. Create AGENTS.md child nodes for directories with distinct responsibilities

Focus on information that would help someone unfamiliar with the codebase navigate and fix bugs safely."""
