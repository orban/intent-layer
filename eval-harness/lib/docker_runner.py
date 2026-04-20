# lib/docker_runner.py
from __future__ import annotations
import logging
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

logger = logging.getLogger(__name__)

# Remote Docker host for native x86 execution (avoids QEMU on Apple Silicon).
# Set EVAL_DOCKER_HOST=chronos to enable.  Workspace files are synced via
# tar-over-SSH to the remote host; Docker runs there with native bind mounts.
REMOTE_DOCKER_HOST: str | None = os.environ.get("EVAL_DOCKER_HOST")
REMOTE_WORKSPACE_BASE: str = os.environ.get("EVAL_REMOTE_WORKSPACE_BASE", "/tmp/eval-workspaces")

# SSH options to prevent indefinite hangs when the agent drops keys or the
# remote becomes unreachable.  ConnectTimeout caps the initial handshake,
# ServerAlive detects dead connections mid-transfer.
_SSH_OPTS = [
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ControlMaster=auto",
    "-o", "ControlPath=/tmp/ssh-eval-%r@%h:%p",
    "-o", "ControlPersist=300",
]

# Timeout (seconds) for sync operations (mkdir, tar upload/download).
# These are workspace-sized transfers (~20-50 MB), not Docker execution,
# so 5 minutes is generous.
_SYNC_TIMEOUT = 300


@dataclass
class DockerResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    # Wall-clock instrumentation. invoked_at is when Popen was called on
    # `docker run`; first_byte_at is when the container emitted its first
    # stdout/stderr line (proxy for "container is running"); finished_at is
    # when the subprocess returned. The gap between invoked_at and
    # first_byte_at ≈ Docker daemon queue + image pull + container create.
    # first_byte_at is None on the fast (non-streaming) path.
    invoked_at: str | None = None
    first_byte_at: str | None = None
    finished_at: str | None = None


# ---------------------------------------------------------------------------
# Remote helpers (tar-over-SSH workspace ↔ remote host)
# ---------------------------------------------------------------------------

def _sync_to_remote(local_path: str, remote_host: str, remote_path: str) -> None:
    """Sync local workspace to remote host via tar-over-SSH.

    Uses tar piped through SSH instead of rsync, because some hosts
    (e.g. UGREEN NAS) run an rsync daemon that intercepts all rsync
    connections and rejects paths outside configured modules.
    """
    subprocess.run(
        ["ssh", *_SSH_OPTS, remote_host, "mkdir", "-p", remote_path],
        check=True, capture_output=True, timeout=_SYNC_TIMEOUT,
    )
    # tar from local, extract on remote — --delete equivalent via rm first
    subprocess.run(
        ["ssh", *_SSH_OPTS, remote_host, "rm", "-rf", f"{remote_path}/*"],
        check=True, capture_output=True, timeout=_SYNC_TIMEOUT,
    )
    ssh_opts_str = " ".join(_SSH_OPTS)
    subprocess.run(
        f"tar -cf - -C {_sh_quote(local_path)} . | ssh {ssh_opts_str} {remote_host} 'tar -xf - -C {_sh_quote(remote_path)}'",
        shell=True, check=True, capture_output=True, timeout=_SYNC_TIMEOUT,
    )


_SYNC_BACK_EXCLUDES = [
    ".venv", "node_modules", "__pycache__", ".tox",
    "*.pyc", ".mypy_cache", ".pytest_cache",
]


def _sync_from_remote(remote_host: str, remote_path: str, local_path: str) -> None:
    """Sync remote workspace back to local via tar-over-SSH.

    Excludes large build artifacts (.venv, node_modules, etc.) that Claude may
    have created during execution — we only need source changes and test results.
    """
    excludes = " ".join(f"--exclude={_sh_quote(e)}" for e in _SYNC_BACK_EXCLUDES)
    ssh_opts_str = " ".join(_SSH_OPTS)
    subprocess.run(
        f"ssh {ssh_opts_str} {remote_host} 'tar -cf - {excludes} -C {_sh_quote(remote_path)} .' | tar -xf - -C {_sh_quote(local_path)}",
        shell=True, check=True, capture_output=True, timeout=_SYNC_TIMEOUT,
    )


def _sh_quote(s: str) -> str:
    """Shell-quote a string for safe use in shell commands."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


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
    escaped = " ".join(_sh_quote(p) for p in docker_parts)
    return ["ssh", *_SSH_OPTS, remote_host, escaped]


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
    """Sync workspace to remote via tar-over-SSH, run Docker there, sync back."""
    workspace_name = Path(abs_workspace).name
    remote_path = f"{REMOTE_WORKSPACE_BASE}/{workspace_name}"

    # 1. Sync workspace to remote
    try:
        _sync_to_remote(abs_workspace, remote_host, remote_path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return DockerResult(
            exit_code=-1, stdout="",
            stderr=f"sync to remote failed: {e}",
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
        _sync_from_remote(remote_host, remote_path, abs_workspace)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning("sync from remote failed: %s", e)

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
        invoked_at = datetime.now(timezone.utc).isoformat()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
            return DockerResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                invoked_at=invoked_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        except subprocess.TimeoutExpired:
            return DockerResult(
                exit_code=-1, stdout="",
                stderr="Command timed out", timed_out=True,
                invoked_at=invoked_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
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
    # Single-element holder so _drain can write first_byte_at without
    # needing nonlocal; protected by the same lock that guards line_counts.
    first_byte_holder: list[str | None] = [None]
    lock = threading.Lock()

    def _drain(stream, target: list[str], key: str):
        for line in stream:
            target.append(line)
            with lock:
                line_counts[key] += 1
                if first_byte_holder[0] is None:
                    first_byte_holder[0] = datetime.now(timezone.utc).isoformat()
            if log_file:
                log_file.write(f"[{key}] {line}")
                log_file.flush()

    invoked_at = datetime.now(timezone.utc).isoformat()
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

        finished_at = datetime.now(timezone.utc).isoformat()

        if timed_out:
            return DockerResult(
                exit_code=-1,
                stdout="".join(stdout_lines),
                stderr="".join(stderr_lines) or "Command timed out",
                timed_out=True,
                invoked_at=invoked_at,
                first_byte_at=first_byte_holder[0],
                finished_at=finished_at,
            )

        return DockerResult(
            exit_code=proc.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            invoked_at=invoked_at,
            first_byte_at=first_byte_holder[0],
            finished_at=finished_at,
        )
    except OSError as e:
        return DockerResult(
            exit_code=-1, stdout="",
            stderr=f"Failed to start process: {e}",
            invoked_at=invoked_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        if log_file:
            log_file.close()


# ---------------------------------------------------------------------------
# Persistent container API (for AGENTbench: start once, exec many)
# ---------------------------------------------------------------------------

def start_container(
    image: str,
    workdir: str = "/testbed",
    memory: str = "4g",
    cpus: str = "1",
    network: str = "bridge",
    remote_host: str | None = None,
) -> str:
    """Start a persistent container. Returns container name."""
    name = f"eval-{uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "-d", "--name", name,
        "--memory", memory, "--cpus", cpus,
        "--network", network, "-w", workdir,
        image, "sleep", "infinity",
    ]
    if remote_host:
        escaped = " ".join(_sh_quote(p) for p in cmd)
        cmd = ["ssh", *_SSH_OPTS, remote_host, escaped]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return name


def exec_in_container(
    name: str,
    command: str,
    timeout: int = 120,
    remote_host: str | None = None,
    stream_log: str | Path | None = None,
    heartbeat_interval: int = 20,
    heartbeat_callback: Callable[[float, int, int], None] | None = None,
) -> DockerResult:
    """Run command inside persistent container via docker exec."""
    cmd = ["docker", "exec", name, "bash", "-lc", command]
    if remote_host:
        escaped = " ".join(_sh_quote(p) for p in cmd)
        cmd = ["ssh", *_SSH_OPTS, remote_host, escaped]
    return _exec_cmd(
        cmd, timeout=timeout, stream_log=stream_log,
        heartbeat_interval=heartbeat_interval,
        heartbeat_callback=heartbeat_callback,
    )


def stop_container(name: str, remote_host: str | None = None) -> None:
    """Stop and remove container. Safe to call if container doesn't exist."""
    stop_cmd = ["docker", "stop", "-t", "1", name]
    rm_cmd = ["docker", "rm", "-f", name]
    try:
        if remote_host:
            for c in (stop_cmd, rm_cmd):
                subprocess.run(
                    ["ssh", *_SSH_OPTS, remote_host,
                     " ".join(_sh_quote(p) for p in c)],
                    capture_output=True, timeout=30,
                )
        else:
            for c in (stop_cmd, rm_cmd):
                subprocess.run(c, capture_output=True, timeout=30)
    except Exception:
        pass  # best-effort cleanup


@contextmanager
def persistent_container(image: str, **kwargs):
    """Context manager for persistent container lifecycle."""
    name = start_container(image, **kwargs)
    try:
        yield name
    finally:
        stop_container(name, remote_host=kwargs.get("remote_host"))


def copy_into_container(
    name: str,
    local_dir: str,
    container_dir: str,
    remote_host: str | None = None,
    excludes: list[str] | None = None,
) -> None:
    """Overlay local directory onto container path via tar pipe.

    Excludes .git by default (200-400 MB for large repos).
    """
    exclude_args = ["--exclude=.git"]
    for e in (excludes or []):
        exclude_args.append(f"--exclude={e}")
    exclude_str = " ".join(exclude_args)

    if remote_host:
        ssh_opts_str = " ".join(_SSH_OPTS)
        subprocess.run(
            f"tar -cf - {exclude_str} -C {_sh_quote(local_dir)} . | "
            f"ssh {ssh_opts_str} {remote_host} "
            f"'docker exec -i {_sh_quote(name)} tar -xf - -C {_sh_quote(container_dir)}'",
            shell=True, check=True, capture_output=True, timeout=_SYNC_TIMEOUT,
        )
    else:
        subprocess.run(
            f"tar -cf - {exclude_str} -C {_sh_quote(local_dir)} . | "
            f"docker exec -i {_sh_quote(name)} tar -xf - -C {_sh_quote(container_dir)}",
            shell=True, check=True, capture_output=True, timeout=_SYNC_TIMEOUT,
        )


def cleanup_stale_containers(remote_host: str | None = None) -> None:
    """Remove orphaned eval-* containers from prior crashed runs."""
    cmd = "docker ps -a --filter name=eval- -q | xargs -r docker rm -f"
    try:
        if remote_host:
            subprocess.run(
                ["ssh", *_SSH_OPTS, remote_host, cmd],
                capture_output=True, timeout=30,
            )
        else:
            subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
    except Exception:
        pass  # best-effort
