# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run one workflow member in the Claude Code terminal lifecycle."""

import asyncio
import json
import os
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from fore_rsi.config import AgentConfig, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base_runtime import AgentRuntime, MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.claude_code.record_file import (
    get_claude_project_link,
    link_project_directory,
    prepare_claude_profile,
    prepare_claude_session,
    remove_project_link,
)
from fore_rsi.rsi_workflows.agent_runtimes.installation import get_or_install_cli
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool, ToolMcpHost
from fore_rsi.utils.paths import write_private_text
from fore_rsi.utils.terminal import run_terminal


class ClaudeCodeAgentRuntime(AgentRuntime):
    """Run Claude Code with a persistent member conversation and project alias."""

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
        """Create a Claude Code runtime with serialized prompt delivery."""
        super().__init__(
            agent_config,
            workflow_directory,
            workgroup_name=workgroup_name,
            agent_name=agent_name,
            tool_mcp_host=tool_mcp_host,
            tools=tools,
        )
        self.claude_project_name: str | None = None
        self.conversation_id: str | None = None
        self.initial_prompt_pending = False
        self.message_tail: asyncio.Task[None] | None = None

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Submit a queue or steer prompt through Claude Code's documented controls."""
        if mode not in {"queue", "steer"}:
            raise ValueError(f"Unsupported Claude Code message delivery mode: {mode!r}")
        if self.terminal_id is None:
            raise RuntimeError("Start the Claude Code member before sending a message.")

        async with self.message_lock:
            previous_message = self.message_tail

            async def deliver() -> None:
                if previous_message is not None:
                    await previous_message
                if mode == "steer":
                    if self.initial_prompt_pending:
                        await self.submit_initial_prompt(message)
                        self.initial_prompt_pending = False
                    else:
                        await self.submit_steer_prompt(message)
                elif self.initial_prompt_pending:
                    await self.submit_initial_prompt(message)
                    self.initial_prompt_pending = False
                else:
                    await self.run_resumed_prompt(message)

            message_task = asyncio.create_task(deliver())
            self.message_tail = message_task
            message_task.add_done_callback(self.consume_message_error)

    async def wait_for_settle(self) -> None:
        """Wait for the submitted Claude Code prompt to settle."""
        message_task = self.message_tail
        if message_task is None:
            raise RuntimeError("Submit a Claude Code message before waiting for settle.")
        try:
            await message_task
        finally:
            if self.message_tail is message_task:
                self.message_tail = None

    async def close(self) -> None:
        """Stop pending prompt delivery, release the pane, and preserve the conversation."""
        message_task = self.message_tail
        self.message_tail = None
        if message_task is not None and not message_task.done():
            message_task.cancel()
            with suppress(asyncio.CancelledError):
                await message_task
        await super().close()

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Claude Code's launcher for startup callers, installing it when missing."""
        return await get_or_install_cli(
            cls.harness_name,
            Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude"),
            "https://claude.ai/install.ps1" if os.name == "nt" else "https://claude.ai/install.sh",
            shell="bash",
        )

    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        system_prompt: str | None = None,
    ) -> list[str]:
        """Prepare Claude Code's persistent conversation, prompt, model, tools, and permissions."""
        self.harness_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        profile = self.profile_directory()
        prepare_claude_profile(profile)
        project_name, session_flag, conversation = prepare_claude_session(
            self.get_agent_file_path(""), profile
        )
        self.claude_project_name = project_name
        self.conversation_id = conversation
        self.initial_prompt_pending = session_flag == "--session-id"

        options: list[str] = ["--dangerously-skip-permissions"]
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
        """Keep Claude Code's project alias with the pane so restore finds its history."""
        if self.claude_project_name is None:
            raise RuntimeError("Claude Code launch arguments were not prepared before pane creation.")
        return {
            "CLAUDE_CODE_PROJECT_DIR_NAME": self.claude_project_name,
            "CLAUDE_CONFIG_DIR": str(self.profile_directory()),
        }

    def profile_directory(self) -> Path:
        """Keep Claude records and session state under this workflow's harness directory."""
        return self.harness_directory / "profile"

    def effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Set the reasoning level for this Claude Code invocation."""
        return ["--effort", effort]

    def tool_mcp_args(self) -> list[str]:
        """Add this member's tool client without replacing other configured MCP servers."""
        config = {"mcpServers": {"fore_rsi": self.tool_stdio_server()}}
        return [f"--mcp-config={json.dumps(config, ensure_ascii=False)}"]

    async def submit_initial_prompt(self, message: str) -> None:
        """Submit the first prompt through the ready Claude Code TUI and wait for its turn."""
        if self.terminal_id is None:
            raise RuntimeError("Start the Claude Code member before sending a message.")
        await run_terminal(
            [
                "agent",
                "prompt",
                self.terminal_id,
                message,
                "--wait",
                "--until",
                "idle",
                "--until",
                "done",
            ],
            self.terminal_session_name,
            capture_output=True,
        )

    async def submit_steer_prompt(self, message: str) -> None:
        """Steer a working turn or submit immediately when Claude is already idle."""
        if self.terminal_id is None:
            raise RuntimeError("Start the Claude Code member before steering it.")
        agent = await self.get_agent()
        if agent is None:
            raise RuntimeError("The Claude Code member is no longer running.")
        status = agent.get("agent_status")
        if status == "blocked":
            raise RuntimeError("Claude Code is blocked before the steering prompt.")
        if status in {"idle", "done"}:
            result = await run_terminal(
                [
                    "agent",
                    "prompt",
                    self.terminal_id,
                    message,
                    "--wait",
                    "--until",
                    "idle",
                    "--until",
                    "done",
                    "--until",
                    "blocked",
                ],
                self.terminal_session_name,
                capture_output=True,
            )
            agent = json.loads(result.stdout)["result"]["agent"]
            if agent.get("agent_status") == "blocked":
                raise RuntimeError("Claude Code is blocked after the steering prompt.")
            return

        if status != "working":
            raise RuntimeError(f"Claude Code cannot steer from state {status!r}.")
        await run_terminal(
            ["agent", "prompt", self.terminal_id, message],
            self.terminal_session_name,
            capture_output=True,
        )
        await run_terminal(
            ["agent", "send-keys", self.terminal_id, "ctrl+x", "ctrl+s"],
            self.terminal_session_name,
            capture_output=True,
        )
        result = await run_terminal(
            [
                "agent",
                "wait",
                self.terminal_id,
                "--until",
                "idle",
                "--until",
                "done",
                "--until",
                "blocked",
            ],
            self.terminal_session_name,
            capture_output=True,
        )
        agent = json.loads(result.stdout)["result"]["agent"]
        if agent.get("agent_status") == "blocked":
            raise RuntimeError("Claude Code is blocked after the steering prompt.")

    async def run_resumed_prompt(self, message: str) -> None:
        """Run one documented headless turn against the member's existing conversation."""
        if self.conversation_id is None or self.claude_project_name is None:
            raise RuntimeError("Prepare the Claude Code conversation before sending a message.")
        executable = await self.ensure_installed()
        command = [
            str(executable),
            "-p",
            "--resume",
            self.conversation_id,
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if self.agent_config.model is not None:
            command.extend(["--model", self.agent_config.model])
        if self.agent_config.effort is not None:
            command.extend(self.effort_args(self.agent_config.effort))
        instructions = self.get_agent_file_path(".instructions.md")
        if instructions.is_file():
            command.extend(["--append-system-prompt-file", str(instructions)])
        command.extend([*self.tool_mcp_args(), message])
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=Path.cwd(),
            env={
                **os.environ,
                "CLAUDE_CONFIG_DIR": str(self.profile_directory()),
                "CLAUDE_CODE_PROJECT_DIR_NAME": self.claude_project_name,
            },
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_task = asyncio.create_task(process.stderr.read()) if process.stderr is not None else None
        result: dict[str, object] | None = None
        try:
            if process.stdout is None:
                raise RuntimeError("Claude Code did not expose stream output.")
            while line := await process.stdout.readline():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "result":
                    result = event
            returncode = await process.wait()
            stderr = await stderr_task if stderr_task is not None else b""
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            if stderr_task is not None:
                stderr_task.cancel()
                with suppress(asyncio.CancelledError):
                    await stderr_task
            raise

        details = stderr.decode("utf-8", errors="replace").strip()
        if returncode != 0:
            raise RuntimeError(f"Claude Code command failed: {details or returncode}")
        if result is None:
            raise RuntimeError("Claude Code ended without a stream result.")
        if result.get("is_error") or result.get("subtype") not in {None, "success"}:
            raise RuntimeError(str(result.get("result") or result.get("subtype") or "Claude Code turn failed."))

    def consume_message_error(self, message_task: asyncio.Task[None]) -> None:
        """Retrieve an asynchronous prompt error until the workflow awaits the task."""
        if not message_task.cancelled():
            message_task.exception()

    @classmethod
    def remove_workflow_storage(cls, workflow_directory: Path) -> None:
        """Remove Claude project links whose targets belong to this workflow."""
        claude_directory = workflow_directory / "harnesses" / "claude"
        for record in claude_directory.glob("member-*.session"):
            binding = json.loads(record.read_bytes())
            conversation = str(binding["id"])
            profile = Path(binding.get("profile") or binding["home"])
            project_directory = claude_directory / "projects" / "agents" / record.stem
            remove_project_link(
                get_claude_project_link(profile, conversation), project_directory
            )
