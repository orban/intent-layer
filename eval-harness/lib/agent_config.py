# lib/agent_config.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Configuration for a CLI-based coding agent.

    All agents are CLI tools that take a prompt and run in a Docker workspace.
    The differences are launch command, install steps, and context filename.
    """
    name: str
    cli_command: str
    model: str
    install_commands: list[str] = field(default_factory=list)
    context_filename: str = "CLAUDE.md"


AGENTS = {
    "claude_code": AgentConfig(
        name="claude_code",
        cli_command='claude --dangerously-skip-permissions --model {model} -p {prompt}',
        model="claude-sonnet-4-5-20250929",
        install_commands=["curl -fsSL https://claude.ai/install.sh | bash"],
        context_filename="CLAUDE.md",
    ),
    "codex": AgentConfig(
        name="codex",
        cli_command='codex exec --yolo --skip-git-repo-check {prompt}',
        model="gpt-5.2-codex",
        install_commands=[
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash",
            '. "$HOME/.nvm/nvm.sh"',
            "nvm install 24",
            "npm install -g @openai/codex@0.55.0",
        ],
        context_filename="AGENTS.md",
    ),
    "qwen_code": AgentConfig(
        name="qwen_code",
        cli_command='qwen --yolo -p {prompt}',
        model="qwen3-30b-coder",
        install_commands=[
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash",
            '. "$HOME/.nvm/nvm.sh"',
            "nvm install 24",
            "npm install -g @qwen-code/qwen-code@0.0.14",
        ],
        context_filename="AGENTS.md",
    ),
}

DEFAULT_AGENT = "claude_code"
