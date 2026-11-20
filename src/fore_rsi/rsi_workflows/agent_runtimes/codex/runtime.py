# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Prepare and run Codex sessions in the workflow-owned terminal lifecycle."""

import asyncio
import json
import os
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from fore_rsi.config import AgentConfig, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime, MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.installation import get_or_install_cli
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool, ToolMcpHost
from fore_rsi.utils.paths import write_private_text


def link_native_directory(link: Path, target: Path) -> None:
    """Expose workflow-owned rollout files at the native location without replacing existing data."""
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except FileExistsError:
        if not link.is_symlink() or link.resolve() != target.resolve():
            raise RuntimeError(f"Native Codex session directory is already in use: {link}") from None


def prepare_codex_profile(profile: Path) -> None:
    """Link Codex's user settings and credentials into the workflow-owned profile."""
    origin = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    origin.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    if profile.resolve() == origin:
        return

    names = (
        "config.toml",
        "auth.json",
        "AGENTS.md",
        "AGENTS.override.md",
        "rules",
        "skills",
        "hooks.json",
        "hooks",
        "plugins",
        "agents",
        *(path.name for path in origin.glob("*.config.toml")),
    )
    for name in names:
        source, link = origin / name, profile / name
        if link.is_symlink():
            if link.resolve() != source.resolve():
                raise ValueError("This Codex conversation belongs to a different CODEX_HOME.")
        elif not link.exists() and (source.exists() or name == "auth.json"):
            # Codex can write a file-based login through this link without copying credentials.
            link.symlink_to(source, target_is_directory=source.is_dir())


def get_codex_thread(record: Path, sessions: Path) -> str | None:
    """Pin the member's root Codex thread, discovering it only inside its rollout directory."""
    if record.exists():
        return str(UUID(record.read_text(encoding="utf-8").strip()))

    roots: set[str] = set()
    for path in sessions.glob("*/*/*/rollout-*.jsonl"):
        with path.open(encoding="utf-8") as stream:
            line = stream.readline()
        if not line:
            continue
        first = json.loads(line)
        metadata = first.get("payload", {})
        if (
            first.get("type") == "session_meta"
            and metadata.get("source") == "cli"
            and not metadata.get("forked_from_id")
            and not metadata.get("parent_thread_id")
        ):
            roots.add(str(UUID(metadata["id"])))

    if len(roots) > 1:
        raise RuntimeError(f"Cannot identify one root Codex conversation in {sessions}.")
    if not roots:
        return None
    thread = roots.pop()
    write_private_text(record, thread + "\n")
    return thread


class CodexAgentRuntime(AgentRuntime):
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

    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        system_prompt: str | None = None,
    ) -> list[str]:
        """Prepare Codex's profile, prompt, tools, and pinned resume command for this member."""
        self.harness_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        profile = self.native_home()
        sessions = self.harness_directory / "sessions" / self.get_agent_file_path("").name
        link_native_directory(profile / "sessions", sessions)
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
            "--no-daemon",
            "-c",
            f"sqlite_home={json.dumps(str(profile), ensure_ascii=False)}",
            *options,
        ]
        if thread is not None:
            command.extend(["resume", thread])
        return [*command, *arguments]

    def launch_environment(self) -> dict[str, str]:
        """Keep Codex's profile selection with the pane so native restore uses the same state."""
        return {"CODEX_HOME": str(self.native_home())}

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Queue a message through Codex's native queue command after its thread exists."""
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
        except Exception as error:
            self.native_message_error = error

    def native_thread(self) -> str | None:
        """Return the member's pinned Codex thread, discovering it after its first native turn."""
        member = self.get_agent_file_path("")
        return get_codex_thread(member.with_suffix(".id"), self.harness_directory / "sessions" / member.name)

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
            bin_directory = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Programs" / "OpenAI" / "Codex" / "bin"
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
            get_codex_thread(member.with_suffix(".id"), self.harness_directory / "sessions" / member.name)

    def effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Override this invocation's reasoning effort without editing Codex's profile."""
        return ["-c", f"model_reasoning_effort={json.dumps(effort)}"]

    def native_home(self) -> Path:
        """Keep the member's Codex profile beside its workflow record file."""
        return self.harness_directory / "profile"

    def tool_mcp_args(self) -> list[str]:
        """Configure the member's stdio MCP client for this invocation without editing config.toml."""
        options: list[str] = []
        for key, value in self.tool_stdio_server().items():
            options.extend(["-c", f"mcp_servers.fore_rsi.{key}={json.dumps(value, ensure_ascii=False)}"])
        return options
