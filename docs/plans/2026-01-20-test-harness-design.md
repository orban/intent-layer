# Intent Layer Test Harness Design

## Overview

End-to-end integration test harness for intent-layer scripts using pytest.

## Decisions

| Component | Choice |
|-----------|--------|
| Framework | pytest |
| Fixtures | 4 synthetic repos (empty, partial, complete, monorepo) |
| E2E target | claude-skills repo itself |
| CI | GitHub Actions + `make test` |
| Shell helper | `sh(cmd)` function, natural string commands |

## Directory Structure

```
intent-layer/
├── tests/
│   ├── conftest.py              # Pytest fixtures, sh() helper
│   ├── fixtures/
│   │   ├── repo_empty/          # No intent layer
│   │   ├── repo_partial/        # Has CLAUDE.md but no Intent Layer section
│   │   ├── repo_complete/       # Full intent layer setup
│   │   └── repo_monorepo/       # Multiple AGENTS.md files
│   ├── integration/
│   │   ├── test_workflows.py    # Full workflow tests
│   │   └── test_feedback_loop.py
│   └── e2e/
│       └── test_real_repos.py   # Smoke tests against claude-skills
├── pytest.ini
├── Makefile                     # test, test-all, test-e2e targets
└── .github/workflows/test.yml
```

## Fixture Repos

### `repo_empty/` - No intent layer
```
src/
  main.py        # ~500 tokens
  utils.py       # ~300 tokens
README.md
```

### `repo_partial/` - Missing Intent Layer section
```
src/
  app.py
CLAUDE.md        # Has content but no "## Intent Layer"
```

### `repo_complete/` - Full setup
```
src/
  api/
    AGENTS.md
    handlers.py
  core/
    AGENTS.md
    models.py
CLAUDE.md
```

### `repo_monorepo/` - Deep hierarchy for LCA testing
```
packages/
  auth/
    AGENTS.md
  billing/
    AGENTS.md
  shared/
    AGENTS.md
CLAUDE.md
```

## Test Cases

### `test_workflows.py`

```python
class TestDetectState:
    def test_empty_repo_returns_none(self, repo_empty)
    def test_partial_repo_returns_partial(self, repo_partial)
    def test_complete_repo_returns_complete(self, repo_complete)
    def test_recognizes_agents_md_as_root(self, repo_with_agents_md)

class TestEstimateTokens:
    def test_counts_tokens_in_directory(self, repo_empty)
    def test_excludes_generated_files(self, repo_with_node_modules)
    def test_all_candidates_finds_large_dirs(self, repo_complete)

class TestValidateNode:
    def test_valid_node_passes(self, repo_complete)
    def test_oversized_node_fails(self, repo_with_huge_claude_md)
    def test_missing_intent_layer_section_warns(self, repo_partial)

class TestDetectChanges:
    def test_finds_covering_node_for_changed_file(self, repo_complete)
    def test_outputs_leaf_first_order(self, repo_monorepo)
    def test_detects_directly_modified_nodes(self, repo_complete)
```

### `test_feedback_loop.py`

```python
class TestFeedbackLoop:
    def test_change_file_detect_node_validate(self, repo_complete)
```

### `test_real_repos.py`

```python
@pytest.mark.slow
@pytest.mark.e2e
class TestRealRepos:
    def test_claude_skills_repo_structure(self)
    def test_detect_changes_on_self(self)
    def test_validate_skill_files(self)
```

## Core Fixtures (`conftest.py`)

```python
import pytest
import os
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

def sh(cmd, cwd=None):
    """Run shell command, return (stdout, stderr, returncode)."""
    import subprocess
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode

@pytest.fixture
def temp_repo(tmp_path):
    """Create empty git repo in temp directory."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sh("git init && git config user.email 'test@test' && git config user.name 'Test'", cwd=repo)
    return repo

@pytest.fixture
def repo_empty(temp_repo):
    sh(f"cp -r {FIXTURES_DIR}/repo_empty/* . && git add -A && git commit -m init", cwd=temp_repo)
    return temp_repo

@pytest.fixture
def run_script(temp_repo):
    """Run intent-layer script with natural shell syntax."""
    def _run(cmd):
        env = {**os.environ, "PATH": f"{SCRIPTS_DIR}:{os.environ['PATH']}"}
        return sh(cmd, cwd=temp_repo)
    return _run
```

## Makefile Targets

```makefile
test:
	pytest intent-layer/tests/ -v --ignore=intent-layer/tests/e2e

test-all:
	pytest intent-layer/tests/ -v

test-e2e:
	pytest intent-layer/tests/e2e -v -m e2e
```

## GitHub Actions (`.github/workflows/test.yml`)

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pytest
      - run: make test
```

## Implementation Order

1. Create fixture repos with minimal content
2. Write `conftest.py` with `sh()` helper and repo fixtures
3. Write `test_workflows.py` - test each script
4. Write `test_feedback_loop.py` - test full cycle
5. Write `test_real_repos.py` - smoke tests
6. Add `pytest.ini` and Makefile targets
7. Add GitHub Actions workflow
8. Run full test suite, fix any issues
