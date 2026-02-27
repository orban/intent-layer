# lib/agentbench_runner.py
"""AGENTbench-specific execution logic.

Loads instances from HuggingFace (via agentbench_loader), runs them through
Docker + Claude, and returns standard TaskResult objects that flow through
the existing reporter/stats pipeline.

All AGENTbench-specific code is contained here — the existing TaskRunner
class doesn't know about AGENTbench.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from lib.agentbench_loader import AgentbenchInstance
from lib.claude_runner import run_claude
from lib.docker_runner import run_in_docker
from lib.git_ops import clone_repo, checkout_commit, create_baseline_commit, get_diff_stats
from lib.prompt_builder import FLAT_PREAMBLE, INTENT_LAYER_PREAMBLE
from lib.task_runner import Condition, TaskResult, SkillGenerationMetrics

logger = logging.getLogger(__name__)

# Timeout for Docker steps (setup, test runs) — separate from Claude timeout
DOCKER_STEP_TIMEOUT = 300
PRE_VALIDATION_TIMEOUT = 300


def _build_docker_cmd(setup_commands: list[str], commands: list[str]) -> str:
    """Join setup + test commands into a single shell command string."""
    parts = setup_commands + commands
    return " && ".join(parts)


def strip_docs(workspace: Path) -> int:
    """Remove context/doc files that could leak hints, preserving build-required files.

    Keeps README.md (and readme.md variants) because many setup.py/pyproject.toml
    files read them for long_description.  Only strips known AI-context files and
    documentation directories.

    Returns count of files/dirs removed.
    """
    count = 0
    # Remove directories
    for dirname in (".github", "docs", ".claude", ".cursor", ".codex"):
        dirpath = workspace / dirname
        if dirpath.exists():
            shutil.rmtree(dirpath)
            count += 1

    # Remove markdown files, but preserve README variants that builds depend on
    _readme_names = {"readme.md", "readme.rst", "readme.txt", "readme"}
    for md_file in workspace.rglob("*.md"):
        if md_file.name.lower() in _readme_names:
            continue
        md_file.unlink()
        count += 1

    return count


def inject_human_context(workspace: Path, base_repo: str) -> list[str]:
    """Fetch developer context files (.md, .claude/) from repo default branch.

    Returns list of relative paths injected.
    """
    injected = []
    # Clone default branch into a temp location, copy context files
    tmp_head = workspace.parent / f".human-ctx-{os.getpid()}-{threading.get_ident()}"
    try:
        repo_url = f"https://github.com/{base_repo}.git"
        clone_repo(repo_url, str(tmp_head), shallow=True)

        # Copy .md files from root
        for md_file in tmp_head.glob("*.md"):
            dest = workspace / md_file.name
            shutil.copy2(md_file, dest)
            injected.append(md_file.name)

        # Copy context directories
        for dirname in (".claude", ".cursor", ".github"):
            src = tmp_head / dirname
            if src.exists() and src.is_dir():
                dest = workspace / dirname
                shutil.copytree(src, dest, dirs_exist_ok=True)
                for f in dest.rglob("*"):
                    if f.is_file():
                        injected.append(str(f.relative_to(workspace)))
    except subprocess.CalledProcessError:
        logger.warning("Could not fetch HEAD context for %s", base_repo)
    finally:
        if tmp_head.exists():
            shutil.rmtree(tmp_head)

    return injected


def write_test_infrastructure(workspace: Path, instance: AgentbenchInstance) -> None:
    """Write test files, test_file_runner, and repo_test_runner to workspace."""
    resolved_ws = workspace.resolve()
    # Write test files
    for rel_path, content in instance.test_files:
        dest = (workspace / rel_path).resolve()
        if not dest.is_relative_to(resolved_ws):
            raise ValueError(f"Path traversal detected in test_files: {rel_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    # Write test runners
    runner_path = workspace / "run_pr_tests.py"
    runner_path.write_text(instance.test_file_runner, encoding="utf-8")
    runner_path.chmod(0o755)

    repo_runner_path = workspace / "run_tests.py"
    repo_runner_path.write_text(instance.repo_test_runner, encoding="utf-8")
    repo_runner_path.chmod(0o755)


def _parse_test_results(workspace: Path, filename: str) -> dict[str, bool] | None:
    """Parse a test results JSON file. Returns None on failure."""
    results_path = workspace / filename
    if not results_path.exists():
        logger.warning("Test results file missing: %s", results_path)
        return None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Test results not a dict: %s", results_path)
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to parse %s: %s", results_path, e)
        return None


def evaluate_instance(
    workspace: Path,
    instance: AgentbenchInstance,
    docker_image: str,
    timeout: int = DOCKER_STEP_TIMEOUT,
) -> tuple[bool, str]:
    """Two-tier evaluation. Returns (success, test_output_summary).

    Tier 1: Instance tests (test_file_runner → pr_test_results.json)
    Tier 2: Repo regression tests (repo_test_runner → test_results.json)
    Both must pass for success=True.
    """
    parts = []

    # Tier 1: Instance tests
    test_cmd = _build_docker_cmd(instance.setup_commands, instance.test_commands)
    result = run_in_docker(str(workspace), docker_image, test_cmd, timeout=timeout)
    pr_results = _parse_test_results(workspace, "pr_test_results.json")

    if pr_results is None:
        return False, f"INSTANCE: pr_test_results.json missing or corrupt | docker exit={result.exit_code}"

    pr_total = len(pr_results)
    pr_passed = sum(1 for v in pr_results.values() if v)
    pr_all_pass = pr_passed == pr_total
    parts.append(f"INSTANCE: {pr_passed}/{pr_total} passed")

    if not pr_all_pass:
        failed_tests = [k for k, v in pr_results.items() if not v]
        parts.append(f"failed: {', '.join(failed_tests[:5])}")
        return False, " | ".join(parts)

    # Tier 2: Regression tests
    repo_test_cmd = _build_docker_cmd(instance.setup_commands, instance.repo_test_commands)
    result = run_in_docker(str(workspace), docker_image, repo_test_cmd, timeout=timeout)
    repo_results = _parse_test_results(workspace, "test_results.json")

    if repo_results is None:
        # Regression runner failed — instance tests passed though
        parts.append("REGRESSION: test_results.json missing or corrupt")
        return False, " | ".join(parts)

    repo_total = len(repo_results)
    repo_passed = sum(1 for v in repo_results.values() if v)

    # Match paper's evaluation: only fail if a test that PASSED in the golden
    # baseline (repo_test_after_pr_patch) now FAILS.  Pre-existing failures
    # and tests missing from the golden baseline are ignored.
    expected = instance.repo_test_after_pr_patch
    regressions = []
    for test_id, expected_pass in expected.items():
        if not expected_pass:
            continue  # already failing in golden — ignore
        actual_pass = repo_results.get(test_id, True)  # missing defaults to True (paper behavior)
        if not actual_pass:
            regressions.append(test_id)

    golden_pass = sum(1 for v in expected.values() if v)
    golden_total = len(expected)
    repo_ok = not regressions
    parts.append(f"REGRESSION: {repo_passed}/{repo_total} passed (golden: {golden_pass}/{golden_total})")
    if regressions:
        parts.append(f"{len(regressions)} regressions: {', '.join(regressions[:5])}")

    return repo_ok, " | ".join(parts)


def build_prompt(
    problem_description: str,
    condition: Condition,
) -> str:
    """Build prompt from AGENTbench problem_description + condition preamble."""
    preamble = {
        Condition.NONE: "",
        Condition.FLAT_LLM: FLAT_PREAMBLE,
        Condition.HUMAN: INTENT_LAYER_PREAMBLE,  # tells Claude to look for CLAUDE.md/AGENTS.md
        Condition.INTENT_LAYER: INTENT_LAYER_PREAMBLE,
    }[condition]

    return f"""{preamble}Fix the following bug:

{problem_description}

The fix should make the existing tests pass. Do not modify the test files."""


# -- Context generation helpers (used by run_single Step 3) --

# Type alias: (workspace, instance, workspaces_dir, model) -> (input_tokens, output_tokens)
_GenerateFn = Callable[[Path, AgentbenchInstance, Path, str], tuple[int, int]]


def _generate_flat_context(
    workspace: Path, instance: AgentbenchInstance, workspaces_dir: Path, model: str,
) -> tuple[int, int]:
    """Generate flat CLAUDE.md via Claude, dual-write to AGENTS.md."""
    from lib.prompt_builder import build_flat_generation_prompt
    log_dir = workspaces_dir.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stderr_log = log_dir / f"{instance.repo}-{instance.base_sha[:8]}-flat_gen.log"
    result = run_claude(
        str(workspace), build_flat_generation_prompt(), timeout=600, model=model,
        stderr_log=str(stderr_log),
    )
    # Dual-write CLAUDE.md -> AGENTS.md (matching paper behavior)
    claude_md = workspace / "CLAUDE.md"
    agents_md = workspace / "AGENTS.md"
    if claude_md.exists() and not agents_md.exists():
        shutil.copy2(claude_md, agents_md)
    return result.input_tokens, result.output_tokens


def _generate_il_context(
    workspace: Path, plugin_root: str, model: str,
) -> tuple[int, int]:
    """Generate intent-layer context via the skill prompt."""
    from lib.prompt_builder import build_skill_generation_prompt
    result = run_claude(
        str(workspace), build_skill_generation_prompt(plugin_root),
        timeout=600, model=model,
    )
    return result.input_tokens, result.output_tokens


def _inject_cached_context(
    instance: AgentbenchInstance,
    workspace: Path,
    workspaces_dir: Path,
    index_cache,
    model: str,
    cache_key: str,
    generate_fn: _GenerateFn,
) -> SkillGenerationMetrics:
    """Check cache, generate on miss, return metrics. Shared by FLAT_LLM and INTENT_LAYER."""
    gen_start = time.time()
    gen_input_tokens = 0
    gen_output_tokens = 0
    cache_hit = False

    if index_cache:
        repo_url = f"https://github.com/{instance.base_repo}.git"
        cache_entry = index_cache.lookup_repo(repo_url, cache_key)
        if cache_entry:
            index_cache.restore(cache_entry, str(workspace))
            cache_hit = True

    if not cache_hit:
        gen_input_tokens, gen_output_tokens = generate_fn(
            workspace, instance, workspaces_dir, model,
        )

    return SkillGenerationMetrics(
        wall_clock_seconds=time.time() - gen_start,
        input_tokens=gen_input_tokens,
        output_tokens=gen_output_tokens,
        cache_hit=cache_hit,
    )


def run_single(
    instance: AgentbenchInstance,
    condition: Condition,
    rep: int,
    workspaces_dir: Path,
    reference_clones: dict[str, Path],
    index_cache=None,
    claude_timeout: int = 1800,
    model: str = "sonnet",
    progress_callback=None,
) -> TaskResult:
    """Full per-instance execution. Returns a standard TaskResult.

    Steps:
    1. Clone repo at base_sha (from reference clone)
    2. strip_docs()
    3. Inject condition context
    4. write_test_infrastructure()
    5. Pre-validate: instance tests should fail
    6. Create baseline commit
    7. build_prompt() + run_claude()
    8. evaluate_instance()
    9. Return TaskResult
    """
    task_id = instance.instance_id
    start = time.time()
    docker_image = instance.docker_image

    def _progress(step: str, msg: str = ""):
        if progress_callback:
            progress_callback(task_id, condition.value, step, msg)

    # --- Step 1: Setup workspace ---
    _progress("setup", "cloning workspace")
    task_hash = format(hash(task_id) % 0xFFFF, '04x')
    workspace_name = f"{instance.repo}-{instance.base_sha[:8]}-{task_hash}-{condition.value}-r{rep}"
    workspace = workspaces_dir / workspace_name
    if workspace.exists():
        shutil.rmtree(workspace)

    ref_clone = reference_clones.get(instance.base_repo)
    clone_repo(
        f"https://github.com/{instance.base_repo}.git",
        str(workspace),
        shallow=False,
        reference=str(ref_clone) if ref_clone else None,
    )
    checkout_commit(str(workspace), instance.base_sha)

    # --- Step 2: Strip docs ---
    _progress("strip", "removing doc files")
    strip_docs(workspace)

    # --- Step 3: Inject condition context ---
    skill_metrics = None
    _progress("context", f"injecting {condition.value}")

    if condition == Condition.FLAT_LLM:
        skill_metrics = _inject_cached_context(
            instance, workspace, workspaces_dir, index_cache, model,
            cache_key="flat_llm",
            generate_fn=_generate_flat_context,
        )

    elif condition == Condition.HUMAN:
        human_start = time.time()
        files = inject_human_context(workspace, instance.base_repo)
        skill_metrics = SkillGenerationMetrics(
            wall_clock_seconds=time.time() - human_start,
            input_tokens=0,
            output_tokens=0,
            cache_hit=False,
            files_created=files,
        )

    elif condition == Condition.INTENT_LAYER:
        plugin_root = os.environ.get("INTENT_LAYER_PLUGIN_ROOT", "")
        if not plugin_root:
            return TaskResult(
                task_id=task_id, condition=condition, success=False,
                test_output="", wall_clock_seconds=time.time() - start,
                input_tokens=0, output_tokens=0, tool_calls=0,
                lines_changed=0, files_touched=[], rep=rep,
                error="[infrastructure] INTENT_LAYER_PLUGIN_ROOT not set",
            )
        skill_metrics = _inject_cached_context(
            instance, workspace, workspaces_dir, index_cache, model,
            cache_key="intent_layer",
            generate_fn=lambda ws, inst, ws_dir, mdl: _generate_il_context(ws, plugin_root, mdl),
        )

    # --- Step 4: Write test infrastructure ---
    _progress("test-infra", "writing test files")
    write_test_infrastructure(workspace, instance)

    # --- Step 5: Pre-validation ---
    _progress("pre-validate", "checking instance tests fail at base")
    test_cmd = _build_docker_cmd(instance.setup_commands, instance.test_commands)
    run_in_docker(  # side effect: writes pr_test_results.json
        str(workspace), docker_image, test_cmd, timeout=PRE_VALIDATION_TIMEOUT
    )
    pre_pr_results = _parse_test_results(workspace, "pr_test_results.json")

    if pre_pr_results is not None and pre_pr_results and all(pre_pr_results.values()):
        return TaskResult(
                task_id=task_id, condition=condition, success=False,
                test_output="", wall_clock_seconds=time.time() - start,
                input_tokens=0, output_tokens=0, tool_calls=0,
                lines_changed=0, files_touched=[], rep=rep,
                error="[pre-validation] instance tests already pass at base_sha",
                skill_generation=skill_metrics,
            )

    # --- Step 6: Baseline commit ---
    _progress("baseline", "creating baseline commit")
    create_baseline_commit(str(workspace))

    # --- Step 7: Run Claude ---
    _progress("claude", "running claude")
    prompt = build_prompt(instance.problem_description, condition)
    log_dir = workspaces_dir.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stderr_log = log_dir / f"{task_id}-{condition.value}-r{rep}.log"

    claude_result = run_claude(
        str(workspace), prompt, timeout=claude_timeout, model=model,
        stderr_log=str(stderr_log),
    )

    if claude_result.timed_out:
        return TaskResult(
            task_id=task_id, condition=condition, success=False,
            test_output="", wall_clock_seconds=time.time() - start,
            input_tokens=claude_result.input_tokens,
            output_tokens=claude_result.output_tokens,
            tool_calls=claude_result.tool_calls,
            lines_changed=0, files_touched=[], rep=rep,
            error="[timeout] claude timed out",
            skill_generation=skill_metrics,
            exit_code=claude_result.exit_code,
            is_timeout=True,
        )

    # Check for empty run (Claude did nothing)
    if claude_result.tool_calls == 0:
        return TaskResult(
            task_id=task_id, condition=condition, success=False,
            test_output="", wall_clock_seconds=time.time() - start,
            input_tokens=claude_result.input_tokens,
            output_tokens=claude_result.output_tokens,
            tool_calls=0,
            lines_changed=0, files_touched=[], rep=rep,
            error="[empty-run] claude made no tool calls",
            skill_generation=skill_metrics,
            exit_code=claude_result.exit_code,
        )

    # --- Step 8: Evaluate ---
    _progress("evaluate", "running tests")
    success, test_output = evaluate_instance(
        workspace, instance, docker_image, timeout=DOCKER_STEP_TIMEOUT
    )

    # --- Step 9: Collect diff stats ---
    diff = get_diff_stats(str(workspace))

    elapsed = time.time() - start
    return TaskResult(
        task_id=task_id,
        condition=condition,
        success=success,
        test_output=test_output,
        wall_clock_seconds=elapsed,
        input_tokens=claude_result.input_tokens,
        output_tokens=claude_result.output_tokens,
        tool_calls=claude_result.tool_calls,
        lines_changed=diff.lines_changed,
        files_touched=diff.files,
        rep=rep,
        skill_generation=skill_metrics,
        exit_code=claude_result.exit_code,
    )
