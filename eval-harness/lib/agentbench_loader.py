# lib/agentbench_loader.py
"""Load AGENTbench instances from HuggingFace (eth-sri/agentbench)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DATASET_NAME = "eth-sri/agentbench"


@dataclass(frozen=True)
class AgentbenchInstance:
    """Single AGENTbench task instance (immutable, shared across workers)."""
    instance_id: str
    repo: str                                    # "ansible_ansible"
    base_repo: str                               # "ansible/ansible"
    base_sha: str
    docker_image: str
    problem_description: str
    setup_commands: list[str]
    test_files: tuple[tuple[str, str], ...]      # ((path, content), ...) — frozen-compatible
    test_commands: list[str]
    test_file_runner: str
    repo_test_runner: str
    repo_test_commands: list[str]
    repo_test_after_pr_patch: dict[str, bool]
    clean_pr_patch: str | None = None


def load_instances(
    filter_repo: str | None = None,
    filter_ids: list[str] | None = None,
) -> list[AgentbenchInstance]:
    """Load instances from HuggingFace, zip test arrays, parse JSON fields.

    Requires the `datasets` package: pip install datasets
    """
    from datasets import load_dataset

    ds = load_dataset(DATASET_NAME, split="train")
    logger.info("Loaded %d instances from %s", len(ds), DATASET_NAME)

    filter_ids_set = set(filter_ids) if filter_ids else None
    instances: list[AgentbenchInstance] = []

    for row in ds:
        if filter_repo and row["repo"] != filter_repo:
            continue
        if filter_ids_set and row["instance_id"] not in filter_ids_set:
            continue

        names = row["test_file_names"]
        contents = row["test_file_contents"]
        if len(names) != len(contents):
            logger.warning(
                "Skipping %s: test_file_names (%d) != test_file_contents (%d)",
                row["instance_id"], len(names), len(contents),
            )
            continue

        # Parse repo_test_after_pr_patch from JSON string
        rtapp = row.get("repo_test_after_pr_patch", "{}")
        if isinstance(rtapp, str):
            try:
                rtapp = json.loads(rtapp)
            except json.JSONDecodeError:
                logger.warning("Bad JSON in repo_test_after_pr_patch for %s", row["instance_id"])
                rtapp = {}

        instances.append(AgentbenchInstance(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_repo=row["base_repo"],
            base_sha=row["base_sha"],
            docker_image=row["docker_image"],
            problem_description=row["problem_description"],
            setup_commands=row["setup_commands"],
            test_files=tuple(zip(names, contents)),
            test_commands=row["test_commands"],
            test_file_runner=row["test_file_runner"],
            repo_test_runner=row["repo_test_runner"],
            repo_test_commands=row["repo_test_commands"],
            repo_test_after_pr_patch=rtapp,
            clean_pr_patch=row.get("clean_pr_patch"),
        ))

    logger.info("Loaded %d instances (after filters)", len(instances))
    return instances
