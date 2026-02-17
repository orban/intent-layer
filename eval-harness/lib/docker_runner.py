# lib/docker_runner.py
from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass


@dataclass
class DockerResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_in_docker(
    workspace: str,
    image: str,
    command: str,
    timeout: int = 120,
    memory: str = "4g",
    cpus: str = "2",
    cache_volume: str | None = "eval-harness-pipcache"
) -> DockerResult:
    """Run a command in a Docker container with workspace mounted.

    Args:
        cache_volume: Docker named volume for pip/uv cache persistence.
            Survives across container runs, so ``uv sync`` only downloads
            packages once. Set to None to disable.
    """
    # Docker requires absolute paths for bind mounts
    abs_workspace = os.path.abspath(workspace)
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{abs_workspace}:/work",
    ]
    if cache_volume:
        cmd.extend(["-v", f"{cache_volume}:/root/.cache"])
    cmd.extend([
        "-w", "/work",
        "--network", "host",
        "--memory", memory,
        "--cpus", cpus,
        image,
        "sh", "-c", command
    ])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return DockerResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False
        )
    except subprocess.TimeoutExpired:
        return DockerResult(
            exit_code=-1,
            stdout="",
            stderr="Command timed out",
            timed_out=True
        )
