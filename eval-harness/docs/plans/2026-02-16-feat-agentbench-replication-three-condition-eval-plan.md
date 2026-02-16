---
title: "feat: Add 3-condition eval for AGENTbench replication"
type: feat
date: 2026-02-16
revised: 2026-02-16
---

# feat: Add 3-condition eval for AGENTbench replication

## Overview

Extend the eval-harness from a 2-condition (with/without skill) to a 3-condition (None / Flat LLM / Intent Layer) A/B/C testing framework. This enables a direct replication and dispute of the "Evaluating AGENTS.md" paper (arxiv 2602.11988v1), which claims LLM-generated context files hurt coding agent performance.

The paper tested flat, single-file context from `/init`. We hypothesize that Intent Layer's hierarchical approach (root CLAUDE.md + child AGENTS.md nodes with mined pitfalls and contracts) produces different results. By using the paper's own benchmark repos with an additional condition, we isolate whether the problem is context files in general or the *structure* of those files.

## Problem Statement

The eval-harness currently supports only two conditions (`WITHOUT_SKILL` / `WITH_SKILL`). To replicate the paper's methodology and add our differentiator, we need:

1. A third "Flat LLM" condition that generates a single CLAUDE.md (matching the paper's approach)
2. Proper context file stripping so the "None" baseline is truly bare
3. A reporter that handles 3-way comparison with baseline-relative deltas
4. Task YAML files for the paper's Python repositories
5. Cache keys that distinguish between generation types

## Proposed Solution

Rename conditions to `NONE` / `FLAT_LLM` / `INTENT_LAYER`, add context-file stripping before any generation, include condition in cache keys, update the reporter for 3-condition comparison, and add `--condition` and `--model` CLI flags. Start with Claude Code, then add Codex and Qwen Code as additional agents in a follow-on phase to match the paper's full multi-agent matrix.

## Reuse Strategy

**Copy verbatim** (exact string constants for experimental faithfulness):

| What | Source | Target |
|------|--------|--------|
| `_CLAUDE_CODE_INIT_PROMPT` | `init_planner.py:60-80` | `lib/prompt_builder.py` — FLAT_LLM generation prompt |
| Universal stripping pattern | `agentbench.py:59-64` | `lib/task_runner.py` — `_strip_context_files()` |
| Dual-write pattern (AGENTS.md + CLAUDE.md) | `init_planner.py:187-188` | `lib/task_runner.py` — FLAT_LLM post-generation |
| Per-repo doc stripping commands | `remove_docs.py` | Task YAML `strip_extra` field (per-repo, not universal) |

**Reimplement in our architecture**:

| Concept | Their approach | Our approach |
|---------|---------------|--------------|
| Task instances | HuggingFace dataset (gated, 401) | YAML task files with equivalent fields |
| Docker execution | `Environment` class | Our `docker_runner.py` |
| Plan caching | JSON + thread lock | Our `IndexCache` with condition in key |
| Agent execution | Multi-agent `Generator` + `CLIAgent` | Direct CLI call (Claude first, then Codex + Qwen) |
| Result collection | jsonlines + trace format | `TaskResult` + reporter |

**Skip entirely**: `benchmark_generator/`, research planners, LiteLLM proxy, multi-agent configs.

Reference copy: `eval-harness/docs/reference/agentbench-harness/` (shallow clone for prompt/pattern lookup).

## Known Methodological Differences from the Paper

These are intentional or unavoidable deviations that affect comparability:

1. **Claude CLI vs model API for FLAT_LLM generation.** The paper generates CLAUDE.md via a pure LLM text call (`generator.run(task=prompt)`). Our harness uses `run_claude()` which invokes Claude CLI with tool access. Claude CLI will explore the repo during flat generation, producing richer output. This is arguably a *better* flat generation (and closer to what real `/init` does), but it means our FLAT_LLM condition is not byte-identical to the paper's.

2. **Single strip vs double strip.** The paper strips context files twice: once before generation (`init_planner.py:179`) and once after (`init_planner.py:184-185`), then writes fresh files. We strip once (after Docker setup, before generation). The second strip in the paper catches context files Claude might create during generation beyond the intended scope. We handle this by constraining the generation prompt, not by post-generation cleanup.

3. **Task sourcing.** The paper's HuggingFace dataset is gated (401). We mine our own tasks from the same repos using `eval-harness scan` and manual curation. Task difficulty distribution may differ.

## Technical Approach

### Implementation Phases

#### Phase 1: 3-condition runner + CLI

The full runner change: enum, stripping, generation routing, preambles, cache keys, and CLI flags. After this phase, all 3 conditions work end to end.

**`lib/task_runner.py`** — Rename Condition enum:
```python
class Condition(Enum):
    NONE = "none"
    FLAT_LLM = "flat_llm"
    INTENT_LAYER = "intent_layer"
```

**`lib/task_runner.py`** — Add context stripping. The universal strip matches the paper's exact pattern (`agentbench.py:59-64`). Additional targets (`.cursorrules`, `.cursor/rules/`, `.clinerules`, `.codex/`, `.claude/`) go in per-repo task YAML as `strip_extra`, not in the universal function:
```python
def _strip_context_files(self, workspace: str) -> list[str]:
    """Remove AI context files from workspace. Returns list of removed paths.

    Uses the paper's exact universal pattern:
      find . -type f \( -name "AGENTS.md" -o -name "CLAUDE.md" \) -print -delete
      rm -rf .github

    Per-repo extras (e.g., .cursorrules, .codex/) are handled separately
    via the task's strip_extra field, matching the paper's per-repo
    CLEANUP_COMMANDS in remove_docs.py.
    """
```

**Ordering**: Call `_strip_context_files()` in `run()` AFTER Docker setup (`_setup_workspace` + `docker.setup()`), BEFORE generation. This matches the paper's ordering where `remove_agents_md_files` runs during `plan()` after `setup()`. The method is a no-op (returns empty list) if no matching files exist.

**`lib/task_runner.py`** — Route generation by condition:
```python
if condition == Condition.INTENT_LAYER:
    prompt = build_skill_generation_prompt()
elif condition == Condition.FLAT_LLM:
    prompt = build_flat_generation_prompt()
# NONE: no generation, stripping already happened
```

**`lib/task_runner.py`** — Update `_check_or_generate_index` signature to `(self, workspace, repo_url, commit, condition)`. For FLAT_LLM, after generation write the same content to both `AGENTS.md` and `CLAUDE.md` (matching paper's dual-write at `init_planner.py:187-188`).

**`lib/prompt_builder.py`** — Add flat generation prompt (paper's exact `_CLAUDE_CODE_INIT_PROMPT`):
```python
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
```

**`lib/prompt_builder.py`** — Change preamble from `bool` to `str | None`. Replace existing `AGENTS_MD_PREAMBLE` and `with_agents_preamble: bool` with explicit preamble selection:
```python
FLAT_PREAMBLE = """Before making changes, read the CLAUDE.md file at the project root to understand:
- Project structure and key patterns
- How to run tests

"""

INTENT_LAYER_PREAMBLE = """Before making changes, read the AGENTS.md files (starting with CLAUDE.md at the root) to understand:
- Where relevant code is located
- What pitfalls to avoid
- What contracts must be maintained

"""
```

Update `_build_prompt(preamble: str | None = None)` — callers pass `None` for NONE, `FLAT_PREAMBLE` for FLAT_LLM, `INTENT_LAYER_PREAMBLE` for INTENT_LAYER. Update `build_task_prompt()` and any other prompt builder functions that currently take `use_preamble: bool`.

**`lib/index_cache.py`** — Include condition in cache key:
```python
def get_cache_key(self, repo_url: str, commit: str, condition: str) -> str:
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    return f"{repo_name}-{commit[:8]}-{condition}"
```

**`lib/cli.py`** — Add `--condition` and `--model` flags:
```python
@click.option("--condition", "-c", multiple=True,
              type=click.Choice(["none", "flat_llm", "intent_layer"]),
              help="Conditions to run (default: all)")
@click.option("--model", default=None,
              help="Claude model to use (e.g., claude-sonnet-4-5-20250929)")
```

Default conditions: all three. Build work queue from selected conditions only. Pass `--model` through to `run_claude()`.

**Tests**:
- Update `test_task_runner.py` fixtures for new enum values
- Test `_strip_context_files()`: create workspace with AGENTS.md, CLAUDE.md, .github/, verify all removed; test empty workspace returns empty list
- Test generation routing: NONE gets no generation, FLAT_LLM uses `build_flat_generation_prompt()`, INTENT_LAYER uses `build_skill_generation_prompt()`
- Test dual-write: FLAT_LLM writes both AGENTS.md and CLAUDE.md
- Test preamble routing: NONE gets `None`, FLAT_LLM gets `FLAT_PREAMBLE`, INTENT_LAYER gets `INTENT_LAYER_PREAMBLE`
- Test cache key includes condition; same repo+commit with different conditions get different keys
- Update `test_cli.py` for `--condition` and `--model` flags

**Files changed**:
- `lib/task_runner.py` — Condition enum, `_strip_context_files()`, `run()` flow, generation routing, preamble passing, `_check_or_generate_index` signature
- `lib/prompt_builder.py` — `build_flat_generation_prompt()`, preamble constants, `bool` → `str | None` signature change
- `lib/index_cache.py` — Condition in cache key
- `lib/cli.py` — `--condition` flag, `--model` flag, work queue generation
- `lib/claude_runner.py` — `--model` passthrough
- `tests/test_task_runner.py` — Enum values, stripping, routing, dual-write, preamble
- `tests/test_prompt_builder.py` — New prompt tests
- `tests/test_index_cache.py` — Cache key tests
- `tests/test_cli.py` — New flag tests

---

#### Phase 2: Reporter update for 3 conditions

Update the reporter from 2 hardcoded conditions to 3 hardcoded conditions with baseline-relative deltas.

**`lib/reporter.py`** — Update `compile_results()`:

Replace `without_skill` / `with_skill` keys with `none` / `flat_llm` / `intent_layer`:
```python
task_result = {
    "task_id": task_id,
    "none": self._serialize_result(none_result),
    "flat_llm": self._serialize_result(flat_result),
    "intent_layer": self._serialize_result(il_result),
    "deltas": {
        "flat_llm": self._compute_single_delta(none_result, flat_result),
        "intent_layer": self._compute_single_delta(none_result, il_result),
    }
}
```

No dynamic N-condition loop. No baseline parameter. NONE is always the baseline. Two explicit delta computations. If a condition is missing (e.g., user ran `--condition none flat_llm`), the missing condition's fields are `null`.

**`lib/reporter.py`** — Update Markdown table to 3 conditions:

Multi-row layout per task:
```markdown
## Results

| Task | Condition | Success | Time (s) | Tokens | Tool Calls | Lines | Δ Time | Δ Tokens |
|------|-----------|---------|----------|--------|------------|-------|--------|----------|
| fix-123 | none | PASS | 45.2 | 12.3k | 18 | 25 | — | — |
| fix-123 | flat_llm | PASS | 52.1 | 15.1k | 22 | 25 | +15.3% | +22.8% |
| fix-123 | intent_layer | PASS | 41.8 | 11.0k | 15 | 20 | -7.5% | -10.6% |
| | | | | | | | | |
| fix-456 | none | FAIL | ... | ... | ... | ... | — | — |
```

**Delta handling**: If the baseline (NONE) has a zero value for a metric (e.g., 0 tool calls because it failed immediately), report the absolute value for non-baseline conditions instead of a percentage delta.

**Tests**: Test 3-condition compilation. Test deltas when baseline is zero. Test missing condition (2 of 3 run) handled gracefully.

**Files changed**:
- `lib/reporter.py` — Hardcoded 3-condition compile, delta, markdown
- `tests/test_reporter.py` — 3-condition result sets, zero-baseline, missing condition

---

#### Phase 3: Task YAML files (pilot)

Create task YAML files for 2-3 of the paper's 12 AGENTbench repos.

**The 12 AGENTbench repos** (from `eth-sri/agentbench` `remove_docs.py`):

| # | Repo | Notes |
|---|------|-------|
| 1 | `ansible/ansible` | Large, complex test infra |
| 2 | `getzep/graphiti` | Graph-based, needs Neo4j |
| 3 | `huggingface/smolagents` | Well-structured, clean tests |
| 4 | `huggingface/transformers` | Very large |
| 5 | `jlowin/fastmcp` | Focused, has .claude + .cursor |
| 6 | `openai/openai-agents-python` | Has .codex dir |
| 7 | `opshin/opshin` | Niche (Cardano smart contracts) |
| 8 | `pdm-project/pdm` | Popular, clean pytest setup |
| 9 | `qodo-ai/pr-agent` | AI tool |
| 10 | `tinygrad/tinygrad` | Hardware-dependent tests |
| 11 | `vibrantlabsai/ragas` | Has .cursor + .claude |
| 12 | `wagtail/wagtail` | Django-based, needs DB |

**Pilot repos** (simple `pytest`, minimal deps):
1. **fastmcp** — small, focused, has AI context dirs to test stripping
2. **pdm** — popular, clean test suite, pure Python
3. **smolagents** — well-structured, HuggingFace ecosystem

**Task YAML schema** (must include these fields):
```yaml
repo:
  url: https://github.com/jlowin/fastmcp
  default_branch: main
  docker:
    image: python:3.11-slim
    setup:
      - pip install -e ".[dev]"
    test_command: pytest
  strip_extra:            # per-repo extra files to strip (optional)
    - .cursorrules
    - .cursor/rules/

tasks:
  - id: fastmcp-fix-123
    description: "Fix TypeError in session handler when connection drops"
    category: simple_fix
    commit: abc123de       # the fix commit (we check out parent, agent must reproduce)
    test_files:            # subset of tests that validate the fix
      - tests/test_session.py::test_connection_drop
    pass_criteria: pytest  # "pytest" = selected test_files pass. Future: "all" = full suite
```

**Pass/fail criteria**: A task passes when `pytest <test_files>` exits 0 after Claude's changes. We run the specified test subset, not the full suite, because some repos have slow or flaky tests unrelated to the fix.

**Step 1**: Mine tasks using `eval-harness scan` or manual curation from recent merged PRs.

**Step 2**: Validate each task with NONE condition:
```bash
eval-harness run --tasks tasks/fastmcp.yaml --condition none --parallel 2 -v
```

**Target**: 7-10 tasks per repo, 20-30 pilot tasks total.

**Estimated wall clock per task**: ~3-8 minutes per task per condition (Docker setup + Claude generation + Claude fix + test run). A full pilot (25 tasks x 3 conditions = 75 runs at ~5 min avg) takes ~6 hours at `--parallel 2`.

**Files created**:
- `tasks/fastmcp.yaml`
- `tasks/pdm.yaml`
- `tasks/smolagents.yaml`

---

#### Phase 4: Multi-agent support (Codex + Qwen)

Add Codex and Qwen Code as agents alongside Claude Code. This creates a full matrix: 3 agents x 3 conditions, matching the paper's multi-agent methodology.

**Paper's agent configurations** (from `generator_constants.py`):

| Agent | CLI | Model | Launch command |
|-------|-----|-------|----------------|
| Claude Code | `claude` | `claude-sonnet-4-5-20250929` | `claude --dangerously-skip-permissions --model {model} -p {prompt}` |
| Codex | `codex` | `gpt-5.2-codex` | `codex exec ... --yolo --skip-git-repo-check {prompt}` |
| Qwen Code | `qwen` | `qwen3-30b-coder` | `qwen --yolo -p {prompt}` |

**`lib/agent_config.py`** — New file. Agent configuration as data, not abstraction:
```python
@dataclass
class AgentConfig:
    name: str           # "claude_code", "codex", "qwen_code"
    cli_command: str     # launch command template with {model}, {prompt} placeholders
    model: str           # default model for this agent
    install_commands: list[str]  # Docker-internal install steps
    context_filename: str  # what context file the agent reads ("CLAUDE.md" or "AGENTS.md")

AGENTS = {
    "claude_code": AgentConfig(
        name="claude_code",
        cli_command='claude --dangerously-skip-permissions --model {model} -p {prompt}',
        model="claude-sonnet-4-5-20250929",
        install_commands=["curl -fsSL https://claude.ai/install.sh | bash"],
        context_filename="CLAUDE.md",
    ),
    "codex": AgentConfig(
        name="codex",
        cli_command='codex exec --yolo --skip-git-repo-check {prompt}',
        model="gpt-5.2-codex",
        install_commands=[
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash",
            '. "$HOME/.nvm/nvm.sh"',
            "nvm install 24",
            "npm install -g @openai/codex@0.55.0",
        ],
        context_filename="AGENTS.md",
    ),
    "qwen_code": AgentConfig(
        name="qwen_code",
        cli_command='qwen --yolo -p {prompt}',
        model="qwen3-30b-coder",
        install_commands=[
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash",
            '. "$HOME/.nvm/nvm.sh"',
            "nvm install 24",
            "npm install -g @qwen-code/qwen-code@0.0.14",
        ],
        context_filename="AGENTS.md",
    ),
}
```

**Design note**: This is a dataclass config, not an abstract `Agent` base class with polymorphic dispatch. All three agents are CLI tools that take a prompt and run in a Docker workspace. The differences are the launch command, install steps, and which context filename they look for. A dict of configs is enough.

**`lib/cli.py`** — Add `--agent` flag:
```python
@click.option("--agent", "-a", multiple=True,
              type=click.Choice(["claude_code", "codex", "qwen_code"]),
              help="Agents to run (default: claude_code)")
```

Default: `claude_code` only (not all, since Codex/Qwen need separate API keys). Work queue becomes `tasks x conditions x agents`.

**`lib/task_runner.py`** — Replace hardcoded `run_claude()` call with agent-dispatch:
```python
def _run_agent(self, agent: AgentConfig, workspace: str, prompt: str) -> AgentOutput:
    """Run any CLI agent in the workspace."""
    cmd = agent.cli_command.format(model=agent.model, prompt=shlex.quote(prompt))
    return self.docker.execute(cmd, workspace)
```

The existing `claude_runner.py` becomes the Claude-specific implementation behind this dispatch for local (non-Docker) runs. For Docker runs, all agents use the same `docker.execute()` path with different commands.

**`lib/index_cache.py`** — Add agent to cache key:
```python
def get_cache_key(self, repo_url: str, commit: str, condition: str, agent: str) -> str:
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    return f"{repo_name}-{commit[:8]}-{condition}-{agent}"
```

Context generation is agent-specific (Claude generates differently from Codex), so the cache must separate them.

**`lib/reporter.py`** — Group results by agent, then by condition:
```markdown
## Results: claude_code

| Task | Condition | Success | Time (s) | Tokens | ...
| fix-123 | none | PASS | 45.2 | 12.3k | ...
| fix-123 | flat_llm | PASS | 52.1 | 15.1k | ...
| fix-123 | intent_layer | PASS | 41.8 | 11.0k | ...

## Results: codex

| Task | Condition | Success | Time (s) | Tokens | ...
```

One section per agent, same 3-condition table structure within each. No cross-agent deltas — each agent is compared against its own NONE baseline.

**FLAT_LLM generation per agent**: The paper uses each agent's own CLI to generate context files (Claude generates CLAUDE.md via `claude -p`, Codex generates via `codex exec`). We match this: FLAT_LLM generation uses the same agent that will run the fix, not always Claude.

**Tests**:
- Test agent config loading and CLI command formatting
- Test cache key includes agent
- Test `--agent` CLI flag filtering
- Test that each agent gets its own results section in the report

**Files changed**:
- `lib/agent_config.py` — New file, agent configs
- `lib/task_runner.py` — Agent dispatch, agent in cache calls
- `lib/cli.py` — `--agent` flag
- `lib/index_cache.py` — Agent in cache key
- `lib/reporter.py` — Per-agent result sections
- `tests/test_agent_config.py` — New tests
- `tests/test_task_runner.py` — Agent dispatch tests
- `tests/test_cli.py` — Agent flag tests

## Deferred (post-pilot backlog)

These are ideas to revisit after the pilot produces real data:

- **Discovery speed metric**: Count tool calls before first Read of a fix-commit file. Only worth building if we see interesting variation in tool call counts.
- **Per-category summary table**: Aggregate success rates by task category. Only useful with 50+ tasks where categories have meaningful N.
- **Bootstrapped confidence intervals**: With N=15-20 per condition, CIs will be wide. Report raw numbers first. Add statistics if we scale to 100+ tasks.
- **Intent Layer component ablation**: Test root-only vs root+children vs root+children+pitfalls. Save for follow-up study.
- **Non-Python repo tasks**: Extend to TypeScript/Go repos from the paper's 12.

## Acceptance Criteria

### Functional Requirements

- [ ] 3 conditions: NONE / FLAT_LLM / INTENT_LAYER all execute correctly
- [ ] NONE strips context files (paper's universal pattern) and runs with a bare prompt
- [ ] FLAT_LLM generates a single CLAUDE.md (dual-write to AGENTS.md) and uses flat preamble
- [ ] INTENT_LAYER generates full hierarchy and uses hierarchy preamble
- [ ] Cache keys include condition — no cross-contamination
- [ ] `--condition` CLI flag selects which conditions to run (default: all)
- [ ] `--model` CLI flag pins Claude model version
- [ ] Reporter shows 3-condition results with NONE-relative deltas
- [ ] Reporter handles 2 of 3 conditions gracefully (missing = null)
- [ ] At least 15 tasks across 2-3 Python repos with defined pass/fail criteria
- [ ] Multi-agent: Codex and Qwen Code run under all 3 conditions
- [ ] `--agent` CLI flag selects which agents to run (default: claude_code)
- [ ] Cache keys include agent — no cross-contamination between agents
- [ ] Reporter groups results per agent

### Quality Gates

- [ ] All existing tests pass after changes
- [ ] New tests cover: stripping, generation routing, dual-write, preamble selection, cache key separation, 3-condition reporter, zero-baseline deltas
- [ ] Pilot run completes end to end: 5 tasks x 3 conditions = 15 runs

## Dependencies & Prerequisites

- **Paper's repo names**: Extracted from `eth-sri/agentbench` `remove_docs.py`
- **Paper's exact prompts**: Copied from `init_planner.py`
- **Reference harness**: Cloned to `eval-harness/docs/reference/agentbench-harness/`
- **Docker + Python**: Target repos must have working pytest suites in Docker
- **Claude CLI**: Installed and configured (Claude Code Max subscription)
- **Codex CLI**: `npm install -g @openai/codex@0.55.0` (Codex Pro subscription)
- **Qwen CLI**: `npm install -g @qwen-code/qwen-code@0.0.14` (API endpoint needed)
- **API budget**: Claude pilot is covered by Max sub. Codex covered by Pro sub. Qwen endpoint cost TBD.

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Paper's repos deleted | Phase 3 blocked | All 12 verified public; 3 pilots selected |
| FLAT_LLM output differs from paper's (Claude CLI explores repo) | Reduced comparability | Acknowledged in methodology section; compare against actual `/init` output |
| Claude model version differs from paper | Results not comparable | `--model` flag pins version; documented in results |
| Python repos have complex test setups | Docker setup fails | Start with simple `pytest` repos; skip special infra |
| 15-20 tasks too few for strong claims | Weak conclusions | Report raw numbers + effect sizes; scale later if promising |
| Codex/Qwen CLI versions change | Reproducibility | Pin exact versions in `agent_config.py` (codex@0.55.0, qwen-code@0.0.14) |
| Qwen Code needs API key/endpoint | Phase 4 blocked | User has access; configure via env vars |
| Agent install in Docker adds latency | Slow runs | Install steps cached in Docker layer; one-time cost per image |

## What We're NOT Building

- Custom test generation (use existing tests)
- Academic paper (blog post target)
- N-condition generalization (hardcode 3)
- Per-category summary (defer until more data)
- Discovery speed metric (defer until pilot results)
- Cost tracking in USD (tokens sufficient)
- Abstract agent base class (dataclass config is enough)
- Cross-agent comparison deltas (each agent vs its own NONE baseline)
- Gemini CLI support (paper includes it but it's lower priority)

## References

### Internal
- Brainstorm: `eval-harness/docs/brainstorms/2026-02-16-agentbench-replication-brainstorm.md`
- Design doc: `eval-harness/docs/plans/2026-01-22-intent-layer-generation-design.md`
- AGENTS.md: `eval-harness/AGENTS.md` (pitfalls section)
- Reference harness: `eval-harness/docs/reference/agentbench-harness/` (shallow clone)
- Paper text: `eval-harness/docs/reference/agentbench-paper.md`

### External
- Paper: https://arxiv.org/html/2602.11988v1
- Paper's code: https://github.com/eth-sri/agentbench
- Paper's dataset: `eth-sri/agentbench` on HuggingFace (gated, 401)

### Key Source Files in Paper's Harness
- `init_planner.py:60-80` — `_CLAUDE_CODE_INIT_PROMPT` (our FLAT_LLM prompt)
- `init_planner.py:179` — Pre-generation strip
- `init_planner.py:184-188` — Post-generation strip + dual-write
- `agentbench.py:59-64` — `remove_agents_md_files()` (our universal strip)
- `remove_docs.py` — Per-repo `CLEANUP_COMMANDS` + the 12 repo names
- `generator_constants.py` — Agent CLI configs (launch commands, install steps, versions)
- `cli_agent.py` — `CLIAgent` class (install → launch → process logs → post-exec)

### Key Files to Modify in Our Harness
- `lib/task_runner.py:29-31` — Condition enum
- `lib/task_runner.py:135-222` — `run()` method
- `lib/task_runner.py:80-133` — `_check_or_generate_index()`
- `lib/prompt_builder.py:5-10` — Preamble (bool → str | None)
- `lib/prompt_builder.py:47-60` — Generation prompt
- `lib/index_cache.py:65-84` — Cache key generation
- `lib/cli.py:79-91` — CLI options
- `lib/cli.py:123-127` — Work queue generation
- `lib/claude_runner.py` — Model passthrough
- `lib/reporter.py:25-57` — Result compilation
- `lib/reporter.py:107-132` — Delta computation
- `lib/reporter.py:155-227` — Markdown table
- `lib/agent_config.py` — New: agent configs (Phase 4)
