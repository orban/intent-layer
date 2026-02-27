# lib/docker_runner.py
from __future__ import annotations
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Remote Docker host for native x86 execution (avoids QEMU on Apple Silicon).
# Set EVAL_DOCKER_HOST=ryo@chronos to enable.  Workspace files are rsynced
# to/from the remote host; Docker runs there with native bind mounts.
REMOTE_DOCKER_HOST: str | None = os.environ.get("EVAL_DOCKER_HOST")
REMOTE_WORKSPACE_BASE: str = os.environ.get("EVAL_REMOTE_WORKSPACE_BASE", "/tmp/eval-workspaces")


@dataclass
class DockerResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


# ---------------------------------------------------------------------------
# Remote helpers (rsync workspace ↔ remote host)
# ---------------------------------------------------------------------------

def _rsync_to_remote(local_path: str, remote_host: str, remote_path: str) -> None:
    """Sync local workspace to remote host. Creates remote dir if needed."""
    subprocess.run(
        ["ssh", remote_host, "mkdir", "-p", remote_path],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["rsync", "-az", "--delete", f"{local_path}/", f"{remote_host}:{remote_path}/"],
        check=True, capture_output=True,
    )


def _rsync_from_remote(remote_host: str, remote_path: str, local_path: str) -> None:
    """Sync remote workspace back to local (picks up test result files etc)."""
    subprocess.run(
        ["rsync", "-az", f"{remote_host}:{remote_path}/", f"{local_path}/"],
        check=True, capture_output=True,
    )


def _remote_docker_cmd(
    remote_host: str,
    remote_workspace: str,
    image: str,
    command: str,
    memory: str,
    cpus: str,
    cache_volume: str | None,
    network: str,
) -> list[str]:
    """Build an ssh command that runs `docker run` on the remote host."""
    docker_parts = [
        "docker", "run", "--rm",
        "-v", f"{remote_workspace}:/work",
    ]
    if cache_volume:
        docker_parts.extend(["-v", f"{cache_volume}:/root/.cache"])
    docker_parts.extend([
        "-w", "/work",
        "--network", network,
        "--memory", memory,
        "--cpus", cpus,
        image,
        "bash", "-lc", command,
    ])
    # Shell-quote each arg for ssh
    escaped = " ".join(_shell_quote(p) for p in docker_parts)
    return ["ssh", remote_host, escaped]


def _shell_quote(s: str) -> str:
    """Simple single-quote escaping for ssh remote commands."""
    if not s or any(c in s for c in " \t\n'\"\\$`!#&|;(){}[]<>?*~"):
        return "'" + s.replace("'", "'\"'\"'") + "'"
    return s


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_in_docker(
    workspace: str,
    image: str,
    command: str,
    timeout: int = 120,
    memory: str = "4g",
    cpus: str = "1",
    cache_volume: str | None = "eval-harness-pipcache",
    stream_log: str | Path | None = None,
    heartbeat_interval: int = 20,
    heartbeat_callback: Callable[[float, int, int], None] | None = None,
    network: str = "bridge",
) -> DockerResult:
    """Run a command in a Docker container with workspace mounted.

    When EVAL_DOCKER_HOST is set, the workspace is rsynced to the remote host
    and Docker runs there natively (no QEMU).  Results are rsynced back.

    Args:
        cache_volume: Docker named volume for pip/uv cache persistence.
            Survives across container runs, so ``uv sync`` only downloads
            packages once. Set to None to disable.
    """
    remote_host = REMOTE_DOCKER_HOST
    abs_workspace = os.path.abspath(workspace)

    if remote_host:
        return _run_remote(
            abs_workspace, remote_host, image, command,
            timeout=timeout, memory=memory, cpus=cpus,
            cache_volume=cache_volume, network=network,
            stream_log=stream_log,
            heartbeat_interval=heartbeat_interval,
            heartbeat_callback=heartbeat_callback,
        )

    return _run_local(
        abs_workspace, image, command,
        timeout=timeout, memory=memory, cpus=cpus,
        cache_volume=cache_volume, network=network,
        stream_log=stream_log,
        heartbeat_interval=heartbeat_interval,
        heartbeat_callback=heartbeat_callback,
    )


# ---------------------------------------------------------------------------
# Remote execution path
# ---------------------------------------------------------------------------

def _run_remote(
    abs_workspace: str,
    remote_host: str,
    image: str,
    command: str,
    *,
    timeout: int,
    memory: str,
    cpus: str,
    cache_volume: str | None,
    network: str,
    stream_log: str | Path | None,
    heartbeat_interval: int,
    heartbeat_callback: Callable[[float, int, int], None] | None,
) -> DockerResult:
    """Rsync workspace to remote, run Docker there, rsync results back."""
    workspace_name = Path(abs_workspace).name
    remote_path = f"{REMOTE_WORKSPACE_BASE}/{workspace_name}"

    # 1. Sync workspace to remote
    try:
        _rsync_to_remote(abs_workspace, remote_host, remote_path)
    except subprocess.CalledProcessError as e:
        return DockerResult(
            exit_code=-1, stdout="",
            stderr=f"rsync to remote failed: {e.stderr if e.stderr else e}",
        )

    # 2. Run Docker on remote via SSH
    cmd = _remote_docker_cmd(
        remote_host, remote_path, image, command,
        memory=memory, cpus=cpus, cache_volume=cache_volume, network=network,
    )

    result = _exec_cmd(
        cmd, timeout=timeout,
        stream_log=stream_log,
        heartbeat_interval=heartbeat_interval,
        heartbeat_callback=heartbeat_callback,
    )

    # 3. Sync results back (even on failure — we want test_results.json)
    try:
        _rsync_from_remote(remote_host, remote_path, abs_workspace)
    except subprocess.CalledProcessError as e:
        logger.warning("rsync from remote failed: %s", e)

    return result


# ---------------------------------------------------------------------------
# Local execution path
# ---------------------------------------------------------------------------

def _run_local(
    abs_workspace: str,
    image: str,
    command: str,
    *,
    timeout: int,
    memory: str,
    cpus: str,
    cache_volume: str | None,
    network: str,
    stream_log: str | Path | None,
    heartbeat_interval: int,
    heartbeat_callback: Callable[[float, int, int], None] | None,
) -> DockerResult:
    """Run Docker locally with bind mount (original behavior)."""
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{abs_workspace}:/work",
    ]
    if cache_volume:
        cmd.extend(["-v", f"{cache_volume}:/root/.cache"])
    cmd.extend([
        "-w", "/work",
        "--network", network,
        "--memory", memory,
        "--cpus", cpus,
        image,
        "bash", "-lc", command,
    ])

    return _exec_cmd(
        cmd, timeout=timeout,
        stream_log=stream_log,
        heartbeat_interval=heartbeat_interval,
        heartbeat_callback=heartbeat_callback,
    )


# ---------------------------------------------------------------------------
# Shared command execution (handles timeout, streaming, heartbeat)
# ---------------------------------------------------------------------------

def _exec_cmd(
    cmd: list[str],
    *,
    timeout: int,
    stream_log: str | Path | None,
    heartbeat_interval: int,
    heartbeat_callback: Callable[[float, int, int], None] | None,
) -> DockerResult:
    """Execute a command with optional streaming and heartbeat."""

    # Fast path: no streaming/heartbeat needed
    if stream_log is None and heartbeat_callback is None:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            return DockerResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return DockerResult(
                exit_code=-1, stdout="",
                stderr="Command timed out", timed_out=True,
            )

    # Streaming path with heartbeat support
    log_file = None
    if stream_log is not None:
        stream_path = Path(stream_log)
        stream_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(stream_path, "w", encoding="utf-8")

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    line_counts = {"stdout": 0, "stderr": 0}
    lock = threading.Lock()

    def _drain(stream, target: list[str], key: str):
        for line in stream:
            target.append(line)
            with lock:
                line_counts[key] += 1
            if log_file:
                log_file.write(f"[{key}] {line}")
                log_file.flush()

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

        out_thread = threading.Thread(
            target=_drain, args=(proc.stdout, stdout_lines, "stdout"), daemon=True,
        )
        err_thread = threading.Thread(
            target=_drain, args=(proc.stderr, stderr_lines, "stderr"), daemon=True,
        )
        out_thread.start()
        err_thread.start()

        start = time.time()
        next_heartbeat = start + max(1, heartbeat_interval)
        timed_out = False

        while True:
            ret = proc.poll()
            now = time.time()
            elapsed = now - start

            if heartbeat_callback and now >= next_heartbeat:
                with lock:
                    stdout_count = line_counts["stdout"]
                    stderr_count = line_counts["stderr"]
                heartbeat_callback(elapsed, stdout_count, stderr_count)
                next_heartbeat = now + max(1, heartbeat_interval)

            if ret is not None:
                break

            if elapsed >= timeout:
                timed_out = True
                proc.kill()
                proc.wait()
                break

            time.sleep(0.2)

        out_thread.join(timeout=5)
        err_thread.join(timeout=5)

        if timed_out:
            return DockerResult(
                exit_code=-1,
                stdout="".join(stdout_lines),
                stderr="".join(stderr_lines) or "Command timed out",
                timed_out=True,
            )

        return DockerResult(
            exit_code=proc.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )
    except OSError as e:
        return DockerResult(
            exit_code=-1, stdout="",
            stderr=f"Failed to start process: {e}",
        )
    finally:
        if log_file:
            log_file.close()
