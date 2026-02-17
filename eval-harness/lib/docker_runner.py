# lib/docker_runner.py
from __future__ import annotations
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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
    cache_volume: str | None = "eval-harness-pipcache",
    stream_log: str | Path | None = None,
    heartbeat_interval: int = 20,
    heartbeat_callback: Callable[[float, int, int], None] | None = None,
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

    # Fast path: keep existing behavior when no streaming/heartbeat is needed.
    if stream_log is None and heartbeat_callback is None:
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
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        out_thread = threading.Thread(
            target=_drain, args=(proc.stdout, stdout_lines, "stdout"), daemon=True
        )
        err_thread = threading.Thread(
            target=_drain, args=(proc.stderr, stderr_lines, "stderr"), daemon=True
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
                stderr=("".join(stderr_lines) or "Command timed out"),
                timed_out=True
            )

        return DockerResult(
            exit_code=proc.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            timed_out=False
        )
    except OSError as e:
        return DockerResult(
            exit_code=-1,
            stdout="",
            stderr=f"Failed to start docker process: {e}",
            timed_out=False
        )
    finally:
        if log_file:
            log_file.close()
