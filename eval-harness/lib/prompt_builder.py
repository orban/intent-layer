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
