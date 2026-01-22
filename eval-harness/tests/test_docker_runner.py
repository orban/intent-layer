# tests/test_docker_runner.py
import shutil
import pytest
from lib.docker_runner import run_in_docker, DockerResult

# Skip all tests in this module if Docker is not available
pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker not available"
)


def test_run_in_docker_returns_result(tmp_path):
    # Create a simple file to cat
    (tmp_path / "hello.txt").write_text("hello world")

    result = run_in_docker(
        workspace=str(tmp_path),
        image="alpine:latest",
        command="cat /work/hello.txt",
        timeout=30
    )

    assert isinstance(result, DockerResult)
    assert result.exit_code == 0
    assert "hello world" in result.stdout


def test_run_in_docker_captures_failure(tmp_path):
    result = run_in_docker(
        workspace=str(tmp_path),
        image="alpine:latest",
        command="exit 1",
        timeout=30
    )

    assert result.exit_code == 1


def test_run_in_docker_timeout(tmp_path):
    result = run_in_docker(
        workspace=str(tmp_path),
        image="alpine:latest",
        command="sleep 60",
        timeout=2
    )

    assert result.timed_out is True
