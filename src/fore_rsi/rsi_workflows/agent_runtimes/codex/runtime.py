# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run one workflow member in the Codex terminal lifecycle."""

import json
import os
from collections.abc import Sequence
from pathlib import Path

from fore_rsi.config import AgentConfig, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base_runtime import AgentRuntime, MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.codex.app_server import CodexAppServer
from fore_rsi.rsi_workflows.agent_runtimes.codex.record_file import (
    get_codex_thread,
    link_profile_sessions,
    prepare_codex_profile,
)
from fore_rsi.rsi_workflows.agent_runtimes.installation import get_or_install_cli
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool, ToolMcpHost
from fore_rsi.utils.terminal import PaneLocation


class CodexAgentRuntime(AgentRuntime):
    """Open Codex in a workflow pane and retain each member's thread separately."""

    harness_name = "codex"

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
        """Create a Codex runtime with serialized message delivery."""
        super().__init__(
            agent_config,
            workflow_directory,
            workgroup_name=workgroup_name,
            agent_name=agent_name,
            tool_mcp_host=tool_mcp_host,
            tools=tools,
        )
        self.app_server: CodexAppServer | None = None

    async def start(self, workspace_id: str, *, is_entry: bool = False, system_prompt: str | None = None) -> None:
        """Start one member-local app-server, then attach its native TUI in the workflow pane."""
        if self.app_server is not None:
            raise RuntimeError("This runtime already owns a Codex app-server.")
        profile = self.profile_directory()
        prepare_codex_profile(profile)
        link_profile_sessions(profile / "sessions", self.harness_directory / "sessions" / self.get_agent_file_path("").name)
        server = self.app_server = CodexAppServer(profile)
        settings = ["-c", f"sqlite_home={json.dumps(str(profile))}"]
        if system_prompt is not None:
            settings.extend(["-c", f"developer_instructions={json.dumps(system_prompt)}"])
        if self.tool_mcp is not None:
            settings.extend(self.tool_mcp_args())
        try:
            await server.start(await self.ensure_installed(), settings)
            await super().start(workspace_id, is_entry=is_entry, system_prompt=system_prompt)
        except BaseException:
            await server.close()
            self.app_server = None
            raise

    async def wait_for_agent_ready(self, pane: PaneLocation, agent: dict[str, object]) -> dict[str, object]:
        """Bind the native thread before publishing this member as ready for input."""
        agent = await super().wait_for_agent_ready(pane, agent)
        assert self.app_server is not None
        await self.app_server.attach_member(self.codex_thread(), self.agent_name)
        return agent

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Submit a Codex queue or steer message through the app-server control channel."""
        if mode not in {"queue", "steer"}:
            raise ValueError(f"Unsupported Codex message delivery mode: {mode!r}")
        server = self.app_server
        if server is None:
            raise RuntimeError("Start the Codex member before sending a message.")
        # An older turn can finish while this input waits for the lock or the pane check.
        async with server.register_input() as client_id, self.message_lock:
            if await self.get_agent() is None:
                raise RuntimeError("The Codex member is no longer running.")
            await server.submit_message(client_id, message, mode)

    async def wait_for_settle(self) -> None:
        """Wait for app-server to report completion of the member's submitted inputs."""
        if self.app_server is None:
            raise RuntimeError("Submit a Codex message before waiting for settle.")
        await self.app_server.wait_for_settle()

    async def close(self) -> None:
        """Stop Codex, release the pane, and retain the Codex thread UUID."""
        was_bound = self.terminal_id is not None
        try:
            await super().close()
        finally:
            if self.app_server is not None:
                await self.app_server.close()
                self.app_server = None
        if was_bound:
            member = self.get_agent_file_path("")
            get_codex_thread(
                member.with_suffix(".id"),
                self.harness_directory / "sessions" / member.name,
            )

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Codex's launcher for startup callers, installing it when missing."""
        if "CODEX_INSTALL_DIR" in os.environ:
            bin_directory = Path(os.environ["CODEX_INSTALL_DIR"])
        elif os.name == "nt":
            bin_directory = (
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                / "Programs"
                / "OpenAI"
                / "Codex"
                / "bin"
            )
        else:
            bin_directory = Path.home() / ".local" / "bin"
        return await get_or_install_cli(
            cls.harness_name,
            bin_directory / ("codex.exe" if os.name == "nt" else "codex"),
            (
                "https://chatgpt.com/codex/install.ps1"
                if os.name == "nt"
                else "https://chatgpt.com/codex/install.sh"
            ),
            environment={"CODEX_NON_INTERACTIVE": "1"},
        )

    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        system_prompt: str | None = None,
    ) -> list[str]:
        """Prepare Codex's profile, prompt, tools, and pinned resume command."""
        if self.app_server is None or self.app_server.url is None:
            raise RuntimeError("Start the Codex app-server before attaching the TUI.")
        thread = self.codex_thread()

        options: list[str] = []
        if self.agent_config.model is not None:
            options.extend(["--model", self.agent_config.model])
        if self.agent_config.effort is not None:
            options.extend(self.effort_args(self.agent_config.effort))
        command = [
            str(executable), "--remote", self.app_server.url,
            "--remote-auth-token-env", CodexAppServer.TOKEN_ENV,
        ]
        if thread is not None:
            # Remote resume retains the conversation's permissions; Codex rejects overrides.
            return [*command, "resume", thread, *arguments]
        return [
            *command, "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust",
            *options, *arguments,
        ]

    def launch_environment(self) -> dict[str, str]:
        """Keep Codex's profile selection with the pane so restore uses the same state."""
        if self.app_server is None:
            raise RuntimeError("Start the Codex app-server before attaching the TUI.")
        return {"CODEX_HOME": str(self.profile_directory()), CodexAppServer.TOKEN_ENV: self.app_server.token}

    def profile_directory(self) -> Path:
        """Keep the member's Codex profile beside its workflow record file."""
        return self.harness_directory / "profile"

    def effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Override this invocation's reasoning effort without editing the profile."""
        return ["-c", f"model_reasoning_effort={json.dumps(effort)}"]

    def tool_mcp_args(self) -> list[str]:
        """Configure this member's stdio MCP client without editing the profile."""
        options: list[str] = []
        for key, value in self.tool_stdio_server().items():
            options.extend([
                "-c",
                f"mcp_servers.fore_rsi.{key}={json.dumps(value, ensure_ascii=False)}",
            ])
        return options

    def codex_thread(self) -> str | None:
        """Return the member's pinned Codex thread, discovering it after its first turn."""
        member = self.get_agent_file_path("")
        return get_codex_thread(
            member.with_suffix(".id"),
            self.harness_directory / "sessions" / member.name,
        )
