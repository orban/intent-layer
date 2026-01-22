# lib/prompt_builder.py
from __future__ import annotations


def build_prompt_from_commit_message(message: str) -> str:
    """Build a prompt from a git commit message."""
    return f"""Fix the following bug:

{message}

The fix should make the existing tests pass."""


def build_prompt_from_failing_test(test_output: str) -> str:
    """Build a prompt from failing test output."""
    return f"""The following test is failing:

```
{test_output}
```

Find and fix the bug that causes this test to fail. Do not modify the test itself."""


def build_prompt_from_issue(title: str, body: str) -> str:
    """Build a prompt from a GitHub issue."""
    return f"""Fix the following bug:

**{title}**

{body}

The fix should make the existing tests pass."""
