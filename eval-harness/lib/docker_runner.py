# lib/docker_runner.py
from __future__ import annotations
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
    cpus: str = "2"
) -> DockerResult:
    """Run a command in a Docker container with workspace mounted."""
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace}:/work",
        "-w", "/work",
        "--network", "host",
        "--memory", memory,
        "--cpus", cpus,
        image,
        "sh", "-c", command
    ]

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
