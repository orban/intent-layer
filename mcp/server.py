"""MCP server wrapping Intent Layer bash scripts.

Exposes read_intent and report_learning as MCP tools, and individual
AGENTS.md/CLAUDE.md files as intent:// resources.

Security: All operations are gated by the INTENT_LAYER_ALLOWED_PROJECTS
environment variable (colon-separated list of allowed project roots).
Every path is canonicalized with os.path.realpath() before use.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("intent-layer")

# ---------------------------------------------------------------------------
# Locate plugin root (walk up from this file looking for .claude-plugin/)
# ---------------------------------------------------------------------------

def _find_plugin_root() -> str:
    current = Path(__file__).resolve().parent
    for ancestor in [current, *current.parents]:
        if (ancestor / ".claude-plugin").is_dir():
            return str(ancestor)
    raise RuntimeError(
        "Cannot find plugin root (.claude-plugin/ directory) "
        f"from {__file__}. Is server.py inside the plugin tree?"
    )

PLUGIN_ROOT = _find_plugin_root()

SUBPROCESS_TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

_ALLOWED_PROJECTS_VAR = "INTENT_LAYER_ALLOWED_PROJECTS"
_ALLOWLIST_MISSING_MSG = (
    f"Environment variable {_ALLOWED_PROJECTS_VAR} is not set. "
    "Set it to a colon-separated list of project root paths that this "
    "server is allowed to access. Example:\n"
    f"  export {_ALLOWED_PROJECTS_VAR}=/home/user/project-a:/home/user/project-b"
)


def _get_allowed_projects() -> list[str]:
    """Return canonicalized allowed project roots, or raise if unset."""
    raw = os.environ.get(_ALLOWED_PROJECTS_VAR)
    if not raw:
        raise ValueError(_ALLOWLIST_MISSING_MSG)
    return [os.path.realpath(p) for p in raw.split(":") if p]


def _validate_project_root(project_root: str) -> str:
    """Canonicalize project_root and confirm it's in the allowlist.

    Returns the canonical path on success; raises ValueError otherwise.
    """
    allowed = _get_allowed_projects()
    canonical = os.path.realpath(project_root)
    if canonical not in allowed:
        raise ValueError(
            f"Project root {canonical!r} is not in the allowed projects list. "
            f"Allowed: {allowed}"
        )
    return canonical


def _validate_path_within_project(canonical_root: str, target: str) -> str:
    """Canonicalize target and verify it lives inside canonical_root.

    Returns the canonical target path on success; raises ValueError on
    traversal attempts.
    """
    canonical_target = os.path.realpath(target)
    if canonical_target != canonical_root and not canonical_target.startswith(
        canonical_root + os.sep
    ):
        raise ValueError(
            f"Path {target!r} resolves to {canonical_target!r}, which is "
            f"outside the project root {canonical_root!r}. "
            "Path traversal is not allowed."
        )
    return canonical_target


def _is_intent_file(path: str) -> bool:
    """Return True if path's basename is AGENTS.md or CLAUDE.md."""
    basename = os.path.basename(path)
    return basename in ("AGENTS.md", "CLAUDE.md")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def read_intent(
    project_root: str, target_path: str, sections: str = ""
) -> str:
    """Return merged ancestor context for a path.

    Shells out to resolve_context.sh. The project_root must be listed
    in INTENT_LAYER_ALLOWED_PROJECTS.

    Args:
        project_root: Absolute path to the project root directory.
        target_path: Path (absolute or relative to project_root) to resolve.
        sections: Optional comma-separated section filter
                  (e.g. "Contracts,Pitfalls").
    """
    canonical_root = _validate_project_root(project_root)

    # If target_path is relative, resolve it relative to the project root
    if not os.path.isabs(target_path):
        resolved_target = os.path.join(canonical_root, target_path)
    else:
        resolved_target = target_path
    canonical_target = _validate_path_within_project(
        canonical_root, resolved_target
    )

    script = os.path.join(PLUGIN_ROOT, "scripts", "resolve_context.sh")
    cmd = [script, canonical_root, canonical_target]
    if sections:
        cmd.extend(["--sections", sections])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"resolve_context.sh timed out after {SUBPROCESS_TIMEOUT}s"
        )

    if result.returncode == 0:
        return result.stdout
    if result.returncode == 2:
        return "No Intent Layer coverage for this path."
    # returncode 1 or anything else is an error
    stderr = result.stderr.strip()
    raise ValueError(
        f"resolve_context.sh failed (exit {result.returncode}): {stderr}"
    )


@mcp.tool()
def report_learning(
    project_root: str,
    path: str,
    type: str,
    title: str,
    detail: str,
    agent_id: str = "",
) -> str:
    """Queue a learning report for later triage.

    Shells out to report_learning.sh. The project_root must be listed
    in INTENT_LAYER_ALLOWED_PROJECTS.

    Args:
        project_root: Absolute path to the project root directory.
        path: File or directory the learning relates to.
        type: Learning type (pitfall, check, pattern, insight).
        title: Short title (50 chars max).
        detail: Full description of the learning.
        agent_id: Optional identifier for the reporting agent.
    """
    canonical_root = _validate_project_root(project_root)

    if not os.path.isabs(path):
        resolved_path = os.path.join(canonical_root, path)
    else:
        resolved_path = path
    canonical_path = _validate_path_within_project(
        canonical_root, resolved_path
    )

    script = os.path.join(PLUGIN_ROOT, "scripts", "report_learning.sh")
    cmd = [
        script,
        "--project", canonical_root,
        "--path", canonical_path,
        "--type", type,
        "--title", title,
        "--detail", detail,
    ]
    if agent_id:
        cmd.extend(["--agent-id", agent_id])

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": PLUGIN_ROOT}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"report_learning.sh timed out after {SUBPROCESS_TIMEOUT}s"
        )

    if result.returncode == 0:
        return f"Learning report created successfully.\n{result.stdout.strip()}"

    stderr = result.stderr.strip()
    raise ValueError(
        f"report_learning.sh failed (exit {result.returncode}): {stderr}"
    )


# ---------------------------------------------------------------------------
# Resources: intent:// scheme
# ---------------------------------------------------------------------------


@mcp.resource("intent://{project}/{path}")
def read_intent_resource(project: str, path: str) -> str:
    """Read an individual AGENTS.md or CLAUDE.md file.

    URI format: intent://<project_alias_or_path>/<relative_path>
    Only serves files named AGENTS.md or CLAUDE.md.
    """
    # project may be URL-encoded or an alias; try to match against allowed
    # projects by basename or full path
    allowed = _get_allowed_projects()

    canonical_root = None
    matches = [
        c for c in allowed
        if os.path.basename(c) == project or c == project
    ]
    if len(matches) > 1:
        # Ambiguous basename — use exact match or first match
        exact = [c for c in matches if c == project]
        canonical_root = exact[0] if exact else matches[0]
    elif matches:
        canonical_root = matches[0]

    if canonical_root is None:
        raise ValueError(
            f"Project {project!r} not found in allowed projects. "
            f"Known projects: {[os.path.basename(p) for p in allowed]}"
        )

    target = os.path.join(canonical_root, path)
    canonical_target = _validate_path_within_project(canonical_root, target)

    if not _is_intent_file(canonical_target):
        raise ValueError(
            f"Resource access is limited to AGENTS.md and CLAUDE.md files. "
            f"Requested: {os.path.basename(canonical_target)!r}"
        )

    if not os.path.isfile(canonical_target):
        raise ValueError(f"File not found: {path}")

    with open(canonical_target) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
