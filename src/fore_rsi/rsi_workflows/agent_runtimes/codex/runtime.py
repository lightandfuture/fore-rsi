# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run one workflow member in the Codex terminal lifecycle."""

from collections import deque
import json
import os
from collections.abc import Sequence
from pathlib import Path

from fore_rsi.config import AgentConfig, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base_runtime import AgentRuntime, MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.codex.app_server import (
    CodexAppServer,
    PendingCodexTurn,
)
from fore_rsi.rsi_workflows.agent_runtimes.codex.record_file import (
    get_codex_thread,
    link_profile_sessions,
    prepare_codex_profile,
)
from fore_rsi.rsi_workflows.agent_runtimes.installation import get_or_install_cli
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool, ToolMcpHost
from fore_rsi.utils.terminal import run_terminal


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
        self.pending_message_count = 0
        self.settle_completion_seq: int | None = None
        self.settle_state_change_seq = 0
        self.app_server: CodexAppServer | None = None
        self.pending_app_turns: deque[PendingCodexTurn] = deque()

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Submit a Codex queue or steer message through the app-server control channel."""
        if mode not in {"queue", "steer"}:
            raise ValueError(f"Unsupported Codex message delivery mode: {mode!r}")
        if self.terminal_id is None:
            raise RuntimeError("Start the Codex member before sending a message.")
        thread = self.codex_thread()

        async with self.message_lock:
            agent = await self.get_agent()
            if agent is None:
                raise RuntimeError("The Codex member is no longer running.")
            if thread is None:
                if mode == "steer":
                    raise RuntimeError("Codex has no active thread to steer.")
                if self.pending_message_count == 0:
                    completion_seq = agent.get("completion_seq")
                    state_change_seq = agent.get("state_change_seq")
                    self.settle_completion_seq = (
                        completion_seq if type(completion_seq) is int else None
                    )
                    self.settle_state_change_seq = (
                        state_change_seq if type(state_change_seq) is int else 0
                    )
                self.pending_message_count += 1
                try:
                    await self.submit_initial_prompt(message)
                except BaseException:
                    self.pending_message_count -= 1
                    if self.pending_message_count == 0:
                        self.settle_completion_seq = None
                        self.settle_state_change_seq = 0
                    raise
                return

            app_server = await self.get_app_server()
            self.pending_app_turns.append(
                await app_server.submit_message(thread, message, mode)
            )

    async def wait_for_settle(self) -> None:
        """Wait for the submitted Codex turn to complete through app-server events."""
        if self.pending_app_turns:
            if self.app_server is None:
                raise RuntimeError("Codex app-server control is not running.")
            pending_turn = self.pending_app_turns[0]
            await self.app_server.wait_for_turn(pending_turn)
            self.pending_app_turns.popleft()
            return
        if self.pending_message_count == 0:
            raise RuntimeError("Submit a Codex message before waiting for settle.")
        try:
            agent = await self.wait_for_agent_status("idle", "done", "blocked")
            if self.completion_observed(agent):
                self.settle_completion_seq = self.read_completion_seq(agent)
                self.settle_state_change_seq = self.read_state_change_seq(agent)
                return
            if agent.get("agent_status") == "blocked":
                raise RuntimeError("Codex is blocked before completing the submitted message.")

            agent = await self.wait_for_agent_status("working", "blocked")
            if agent.get("agent_status") == "blocked":
                raise RuntimeError("Codex is blocked while processing the submitted message.")
            agent = await self.wait_for_agent_status("idle", "done", "blocked")
            if agent.get("agent_status") == "blocked":
                raise RuntimeError("Codex is blocked before completing the submitted message.")
            if not self.completion_observed(agent):
                raise RuntimeError("Codex settled without a new completion transition.")
            self.settle_completion_seq = self.read_completion_seq(agent)
            self.settle_state_change_seq = self.read_state_change_seq(agent)
        finally:
            self.pending_message_count -= 1
            if self.pending_message_count == 0:
                self.settle_completion_seq = None
                self.settle_state_change_seq = 0

    async def close(self) -> None:
        """Stop Codex, release the pane, and retain the Codex thread UUID."""
        self.pending_message_count = 0
        self.settle_completion_seq = None
        self.settle_state_change_seq = 0
        self.pending_app_turns.clear()
        app_server = self.app_server
        self.app_server = None
        was_bound = self.terminal_id is not None
        try:
            if app_server is not None:
                await app_server.close()
        finally:
            await super().close()
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
        self.harness_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        profile = self.profile_directory()
        sessions = self.harness_directory / "sessions" / self.get_agent_file_path("").name
        link_profile_sessions(profile / "sessions", sessions)
        prepare_codex_profile(profile)
        thread = get_codex_thread(self.get_agent_file_path(".id"), sessions)

        options: list[str] = []
        if self.agent_config.model is not None:
            options.extend(["--model", self.agent_config.model])
        if self.agent_config.effort is not None:
            options.extend(self.effort_args(self.agent_config.effort))
        if system_prompt is not None:
            options.extend([
                "-c",
                f"developer_instructions={json.dumps(system_prompt, ensure_ascii=False)}",
            ])
        if self.tool_mcp is not None:
            options.extend(self.tool_mcp_args())

        command = [
            str(executable),
            "--dangerously-bypass-approvals-and-sandbox",
            "--dangerously-bypass-hook-trust",
            "-c",
            f"sqlite_home={json.dumps(str(profile), ensure_ascii=False)}",
            *options,
        ]
        if thread is not None:
            command.extend(["resume", thread])
        return [*command, *arguments]

    def launch_environment(self) -> dict[str, str]:
        """Keep Codex's profile selection with the pane so restore uses the same state."""
        return {"CODEX_HOME": str(self.profile_directory())}

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

    async def submit_initial_prompt(self, message: str) -> None:
        """Submit the first prompt through the ready Codex TUI before its thread exists."""
        if self.terminal_id is None:
            raise RuntimeError("Start the Codex member before sending a message.")
        await run_terminal(
            ["agent", "prompt", self.terminal_id, message],
            self.terminal_session_name,
            capture_output=True,
        )

    def codex_thread(self) -> str | None:
        """Return the member's pinned Codex thread, discovering it after its first turn."""
        member = self.get_agent_file_path("")
        return get_codex_thread(
            member.with_suffix(".id"),
            self.harness_directory / "sessions" / member.name,
        )

    async def get_app_server(self) -> CodexAppServer:
        """Start or reuse the control client for this member's Codex profile."""
        if self.app_server is None:
            executable = await self.ensure_installed()
            self.app_server = CodexAppServer(self.profile_directory(), executable)
        await self.app_server.connect()
        return self.app_server

    async def wait_for_agent_status(self, *statuses: str) -> dict[str, object]:
        """Wait for one Terminal agent state and return the observed agent record."""
        if self.terminal_id is None:
            raise RuntimeError("Start the Codex member before waiting for settle.")
        command = ["agent", "wait", self.terminal_id]
        for status in statuses:
            command.extend(["--until", status])
        result = await run_terminal(command, self.terminal_session_name, capture_output=True)
        return json.loads(result.stdout)["result"]["agent"]

    def completion_observed(self, agent: dict[str, object]) -> bool:
        """Return whether Terminal reports a completion after the current baseline."""
        completion_seq = self.read_completion_seq(agent)
        if completion_seq is not None:
            return self.settle_completion_seq is None or completion_seq > self.settle_completion_seq
        state_change_seq = self.read_state_change_seq(agent)
        return (
            state_change_seq > self.settle_state_change_seq
            and agent.get("agent_status") in {"idle", "done"}
        )

    @staticmethod
    def read_completion_seq(agent: dict[str, object]) -> int | None:
        """Read Terminal's optional completion sequence from one agent record."""
        value = agent.get("completion_seq")
        return value if type(value) is int else None

    @staticmethod
    def read_state_change_seq(agent: dict[str, object]) -> int:
        """Read Terminal's state-change sequence from one agent record."""
        value = agent.get("state_change_seq")
        return value if type(value) is int else 0
