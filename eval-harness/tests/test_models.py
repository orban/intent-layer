# tests/test_models.py
import pytest
from lib.models import RepoConfig, DockerConfig, Task, TaskFile


def test_docker_config_parses():
    data = {
        "image": "node:20-slim",
        "setup": ["npm install"],
        "test_command": "npm test"
    }
    config = DockerConfig(**data)
    assert config.image == "node:20-slim"
    assert config.setup == ["npm install"]
    assert config.test_command == "npm test"


def test_task_parses():
    data = {
        "id": "fix-bug-123",
        "category": "simple_fix",
        "pre_fix_commit": "abc123",
        "fix_commit": "def456",
        "test_file": "test/foo.test.js",
        "prompt_source": "commit_message"
    }
    task = Task(**data)
    assert task.id == "fix-bug-123"
    assert task.category == "simple_fix"


def test_task_validates_category():
    with pytest.raises(ValueError):
        Task(
            id="bad",
            category="invalid_category",
            pre_fix_commit="abc",
            fix_commit="def",
            prompt_source="commit_message"
        )


def test_task_file_parses_yaml(tmp_path):
    yaml_content = """
repo:
  url: https://github.com/test/repo
  default_branch: main
  docker:
    image: node:20-slim
    setup:
      - npm install
    test_command: npm test

tasks:
  - id: fix-123
    category: simple_fix
    pre_fix_commit: abc
    fix_commit: def
    prompt_source: commit_message
"""
    f = tmp_path / "tasks.yaml"
    f.write_text(yaml_content)

    task_file = TaskFile.from_yaml(f)
    assert task_file.repo.url == "https://github.com/test/repo"
    assert len(task_file.tasks) == 1
    assert task_file.tasks[0].id == "fix-123"
