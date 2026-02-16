from lib.agent_config import AgentConfig, AGENTS, DEFAULT_AGENT


class TestAgentsRegistry:
    def test_all_three_agents_exist(self):
        assert set(AGENTS.keys()) == {"claude_code", "codex", "qwen_code"}

    def test_default_agent_is_claude_code(self):
        assert DEFAULT_AGENT == "claude_code"


class TestAgentConfigTypes:
    def test_name_is_str(self):
        for agent in AGENTS.values():
            assert isinstance(agent.name, str)

    def test_install_commands_is_list(self):
        for agent in AGENTS.values():
            assert isinstance(agent.install_commands, list)

    def test_all_fields_populated(self):
        for agent in AGENTS.values():
            assert agent.name
            assert agent.cli_command
            assert agent.model
            assert agent.context_filename


class TestCliCommand:
    def test_all_agents_have_prompt_placeholder(self):
        for name, agent in AGENTS.items():
            assert "{prompt}" in agent.cli_command, f"{name} missing {{prompt}}"

    def test_claude_code_has_model_placeholder(self):
        assert "{model}" in AGENTS["claude_code"].cli_command

    def test_claude_code_format_works(self):
        result = AGENTS["claude_code"].cli_command.format(
            model="test-model", prompt="fix the bug"
        )
        assert "test-model" in result
        assert "fix the bug" in result

    def test_codex_format_works(self):
        result = AGENTS["codex"].cli_command.format(prompt="fix the bug")
        assert "fix the bug" in result

    def test_qwen_format_works(self):
        result = AGENTS["qwen_code"].cli_command.format(prompt="fix the bug")
        assert "fix the bug" in result


class TestInstallCommands:
    def test_codex_has_nvm_install(self):
        commands = " ".join(AGENTS["codex"].install_commands)
        assert "nvm" in commands

    def test_qwen_has_nvm_install(self):
        commands = " ".join(AGENTS["qwen_code"].install_commands)
        assert "nvm" in commands


class TestContextFilename:
    def test_claude_code_uses_claude_md(self):
        assert AGENTS["claude_code"].context_filename == "CLAUDE.md"

    def test_codex_uses_agents_md(self):
        assert AGENTS["codex"].context_filename == "AGENTS.md"

    def test_qwen_uses_agents_md(self):
        assert AGENTS["qwen_code"].context_filename == "AGENTS.md"
