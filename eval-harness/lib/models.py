# lib/models.py
from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, field_validator
import yaml


class DockerConfig(BaseModel):
    image: str
    setup: list[str] = []
    test_command: str


class RepoConfig(BaseModel):
    url: str
    default_branch: str = "main"
    docker: DockerConfig
    strip_extra: list[str] = []


class Task(BaseModel):
    id: str
    category: Literal["simple_fix", "targeted_refactor", "complex_fix"]
    pre_fix_commit: str
    fix_commit: str
    test_file: str | None = None
    test_pattern: str | None = None
    prompt_source: Literal["failing_test", "issue", "commit_message"]
    issue_number: int | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid = {"simple_fix", "targeted_refactor", "complex_fix"}
        if v not in valid:
            raise ValueError(f"category must be one of {valid}")
        return v


class TaskFile(BaseModel):
    repo: RepoConfig
    tasks: list[Task]

    @classmethod
    def from_yaml(cls, path: Path) -> TaskFile:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
