# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Codex CLI preparation and runtime contract."""

import asyncio
from collections.abc import Sequence
from contextlib import suppress
import json
import os
from pathlib import Path

from fore_rsi.config import AgentConfig, Config, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base import MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed
from fore_rsi.rsi_workflows.agent_runtimes.named_conversation import NamedConversationRuntime
from fore_rsi.rsi_workflows.agent_runtimes.native_launch import codex_profiles, codex_thread
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost


class CodexAgentRuntime(NamedConversationRuntime):
    """Open Codex in a workflow pane and retain each member's native thread separately."""

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
        """Create a Codex runtime with serialized native message delivery."""
        super().__init__(
            agent_config,
            workflow_directory,
            workgroup_name=workgroup_name,
            agent_name=agent_name,
            tool_mcp_host=tool_mcp_host,
            tools=tools,
        )
        self.native_message_tail: asyncio.Task[None] | None = None
        self.native_message_error: BaseException | None = None

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Queue a message with Codex's native queue command after its thread exists."""
        if mode == "steer":
            raise NotImplementedError(
                "Codex does not expose a documented programmatic checkpoint-steer command."
            )
        if mode != "queue":
            raise ValueError(f"Unsupported Codex message delivery mode: {mode!r}")
        if self.native_message_error is not None:
            raise RuntimeError("A previous native Codex message failed.") from self.native_message_error
        if self.native_thread() is None:
            raise NotImplementedError(
                "Codex native queue requires an existing thread; its initial prompt path is not implemented."
            )

        async with self.message_lock:
            previous_message = self.native_message_tail

            async def deliver() -> None:
                if previous_message is not None:
                    await previous_message
                await self.queue_native_message(message)

            message_task = asyncio.create_task(deliver())
            self.native_message_tail = message_task
            message_task.add_done_callback(self.record_native_message_error)

    def record_native_message_error(self, message_task: asyncio.Task[None]) -> None:
        """Retain an asynchronous native delivery failure for the next workflow boundary."""
        if message_task.cancelled():
            return
        try:
            message_task.result()
        except BaseException as error:
            self.native_message_error = error

    def native_thread(self) -> str | None:
        """Return the member's pinned Codex thread, discovering it after its first native turn."""
        member = self.get_agent_file_path("")
        return codex_thread(member.with_suffix(".id"), self.harness_directory / "sessions" / member.name)

    async def queue_native_message(self, message: str) -> None:
        """Queue one message through Codex's documented native session command."""
        thread = self.native_thread()
        if thread is None:
            raise RuntimeError("Codex has not created a native thread for this member.")
        profile = self.native_home()
        command = [
            str(await self.ensure_installed()),
            "queue",
            "-c",
            f"sqlite_home={json.dumps(str(profile), ensure_ascii=False)}",
            "--thread",
            thread,
            "--message",
            message,
        ]
        await self.run_native_command(command, profile)

    async def run_native_command(self, command: list[str], profile: Path) -> None:
        """Run one Codex control command outside the managed pane and preserve cancellation cleanup."""
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=Path.cwd(),
            env={**os.environ, "CODEX_HOME": str(profile)},
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            raise
        if process.returncode != 0:
            details = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Native Codex command failed: {details or process.returncode}")

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Codex's launcher for startup callers, installing without starting a conversation."""
        if "CODEX_INSTALL_DIR" in os.environ:
            bin_directory = Path(os.environ["CODEX_INSTALL_DIR"])
        elif os.name == "nt":
            bin_directory = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "OpenAI" / "Codex" / "bin"
        else:
            bin_directory = Path.home() / ".local" / "bin"
        return await ensure_cli_installed(
            cls.harness_name,
            bin_directory / ("codex.exe" if os.name == "nt" else "codex"),
            (
                "https://chatgpt.com/codex/install.ps1"
                if os.name == "nt"
                else "https://chatgpt.com/codex/install.sh"
            ),
            environment={"CODEX_NON_INTERACTIVE": "1"},
        )

    async def close(self) -> None:
        """Stop native delivery, release the pane, and retain the Codex thread UUID."""
        message_task = self.native_message_tail
        self.native_message_tail = None
        if message_task is not None and not message_task.done():
            message_task.cancel()
            with suppress(asyncio.CancelledError):
                await message_task
        was_bound = self.terminal_id is not None
        await super().close()
        if was_bound:
            member = self.get_agent_file_path("")
            codex_thread(member.with_suffix(".id"), self.harness_directory / "sessions" / member.name)

    def effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Override this invocation's reasoning effort without editing Codex's profile."""
        return ["-c", f"model_reasoning_effort={json.dumps(effort)}"]

    def native_home(self) -> Path:
        """Keep Codex profile and sign-in state outside the project containing workflow transcripts."""
        return codex_profiles(Config.SESSION_INDEX_PATH.parent, self.terminal_session_name) / self.get_agent_file_path("").name

    def tool_mcp_args(self) -> list[str]:
        """Configure the member's stdio MCP client for this invocation without editing config.toml."""
        options = []
        for key, value in self.stdio_server().items():
            options.extend(["-c", f"mcp_servers.fore_rsi.{key}={json.dumps(value, ensure_ascii=False)}"])
        return options
