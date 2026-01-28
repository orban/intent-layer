# lib/prompt_builder.py
from __future__ import annotations


AGENTS_MD_PREAMBLE = """Before making changes, read the AGENTS.md files (starting with CLAUDE.md at the root) to understand:
- Where relevant code is located
- What pitfalls to avoid
- What contracts must be maintained

"""


def build_prompt_from_commit_message(message: str, with_agents_preamble: bool = False) -> str:
    """Build a prompt from a git commit message."""
    preamble = AGENTS_MD_PREAMBLE if with_agents_preamble else ""
    return f"""{preamble}Fix the following bug:

{message}

The fix should make the existing tests pass."""


def build_prompt_from_failing_test(test_output: str, with_agents_preamble: bool = False) -> str:
    """Build a prompt from failing test output."""
    preamble = AGENTS_MD_PREAMBLE if with_agents_preamble else ""
    return f"""{preamble}The following test is failing:

```
{test_output}
```

Find and fix the bug that causes this test to fail. Do not modify the test itself."""


def build_prompt_from_issue(title: str, body: str, with_agents_preamble: bool = False) -> str:
    """Build a prompt from a GitHub issue."""
    preamble = AGENTS_MD_PREAMBLE if with_agents_preamble else ""
    return f"""{preamble}Fix the following bug:

**{title}**

{body}

The fix should make the existing tests pass."""


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
