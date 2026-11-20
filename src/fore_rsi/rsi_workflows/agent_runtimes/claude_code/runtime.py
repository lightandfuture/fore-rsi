# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Prepare and run Claude Code sessions in the workflow-owned terminal lifecycle."""

import json
import os
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

from fore_rsi.config import AgentConfig, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime, MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.installation import get_or_install_cli
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool, ToolMcpHost
from fore_rsi.utils.paths import write_private_text


def get_claude_project_link(home: Path, conversation: str) -> Path:
    """Return the stable native project alias for one Claude Code conversation."""
    return home / "projects" / f"fore-rsi-{UUID(conversation)}"


def link_native_directory(link: Path, target: Path) -> None:
    """Expose a workflow-owned Claude project without replacing an existing native directory."""
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except FileExistsError:
        if not link.is_symlink() or link.resolve() != target.resolve():
            raise RuntimeError(f"Native Claude project directory is already in use: {link}") from None


def remove_native_link(link: Path, target: Path) -> None:
    """Remove only the Claude project link still owned by this workflow member."""
    if link.is_symlink() and link.resolve() == target.resolve():
        link.unlink()


def prepare_claude_session(member: Path, home: Path) -> tuple[str, str, str]:
    """Bind one persistent conversation UUID to its native Claude project alias."""
    record = member.with_suffix(".session")
    project_directory = member.parent / "projects" / "agents" / member.name
    try:
        binding = json.loads(record.read_bytes())
    except FileNotFoundError:
        binding = {"id": str(uuid4()), "home": None}

    conversation = str(UUID(binding["id"]))
    previous_home = binding["home"]
    if previous_home != str(home):
        if previous_home is not None:
            remove_native_link(
                get_claude_project_link(Path(previous_home), conversation), project_directory
            )
        write_private_text(record, json.dumps({"id": conversation, "home": str(home)}))

    project_link = get_claude_project_link(home, conversation)
    link_native_directory(project_link, project_directory)
    flag = "--resume" if (project_directory / f"{conversation}.jsonl").is_file() else "--session-id"
    return project_link.name, flag, conversation


class ClaudeCodeAgentRuntime(AgentRuntime):
    """Run Claude Code with an explicit member conversation and workflow-owned project alias."""

    harness_name = "claude"

    def __init__(
        self,
        agent_config: AgentConfig,
        workflow_directory: Path,
        *,
        workgroup_name: str,
        agent_name: str,
        tool_mcp_host: ToolMcpHost,
        tools: Sequence[AgentTool] = (),
    ) -> None:
        """Create a Claude Code runtime without starting its native process."""
        super().__init__(
            agent_config,
            workflow_directory,
            workgroup_name=workgroup_name,
            agent_name=agent_name,
            tool_mcp_host=tool_mcp_host,
            tools=tools,
        )
        self.claude_project_name: str | None = None

    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        system_prompt: str | None = None,
    ) -> list[str]:
        """Prepare Claude Code's persistent conversation, prompt, model, and tool arguments."""
        self.harness_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        project_name, session_flag, conversation = prepare_claude_session(
            self.get_agent_file_path(""), self.native_home()
        )
        self.claude_project_name = project_name

        options: list[str] = []
        if self.agent_config.model is not None:
            options.extend(["--model", self.agent_config.model])
        if self.agent_config.effort is not None:
            options.extend(self.effort_args(self.agent_config.effort))
        if system_prompt is not None:
            instructions = self.get_agent_file_path(".instructions.md")
            write_private_text(instructions, system_prompt)
            options.extend(["--append-system-prompt-file", str(instructions)])
        return super().build_launch_command(
            executable,
            [session_flag, conversation, *options, *arguments],
            system_prompt=system_prompt,
        )

    def launch_environment(self) -> dict[str, str]:
        """Keep Claude Code's project alias with the pane so native restore finds this member's history."""
        if self.claude_project_name is None:
            raise RuntimeError("Claude Code launch arguments were not prepared before pane creation.")
        return {"CLAUDE_CODE_PROJECT_DIR_NAME": self.claude_project_name}

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Report that Claude Code has no documented local queue or checkpoint-steer API."""
        if mode not in {"queue", "steer"}:
            raise ValueError(f"Unsupported Claude Code message delivery mode: {mode!r}")
        raise NotImplementedError(
            f"Claude Code has no documented native local {mode} message API for this runtime."
        )

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Claude Code's launcher for startup callers, using its native installer when missing."""
        return await get_or_install_cli(
            cls.harness_name,
            Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude"),
            "https://claude.ai/install.ps1" if os.name == "nt" else "https://claude.ai/install.sh",
            shell="bash",
        )

    def effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Set the reasoning level for this Claude Code invocation."""
        return ["--effort", effort]

    def native_home(self) -> Path:
        """Use the user's Claude Code settings and credential store without copying them."""
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser().resolve()

    def tool_mcp_args(self) -> list[str]:
        """Add this member's tool client without replacing other configured MCP servers."""
        config = {"mcpServers": {"fore_rsi": self.tool_stdio_server()}}
        return [f"--mcp-config={json.dumps(config, ensure_ascii=False)}"]

    @classmethod
    def remove_workflow_storage(cls, workflow_directory: Path) -> None:
        """Remove Claude project links whose targets belong to this workflow."""
        claude_directory = workflow_directory / "harnesses" / "claude"
        for record in claude_directory.glob("member-*.session"):
            binding = json.loads(record.read_bytes())
            conversation = str(UUID(binding["id"]))
            project_directory = claude_directory / "projects" / "agents" / record.stem
            remove_native_link(
                get_claude_project_link(Path(binding["home"]), conversation), project_directory
            )
