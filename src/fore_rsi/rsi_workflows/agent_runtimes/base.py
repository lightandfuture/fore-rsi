# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common lifecycle and input operations for one native agent conversation."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

from fore_rsi.config import HarnessConfig, WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import create_tool_mcp
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost
from fore_rsi.utils.terminal import ensure_terminal_pane, report_terminal_metadata


@dataclass
class AgentTool:
    """A workflow-owned tool whose typed handler defines its public parameters.

    The MCP service awaits the handler on the workflow event loop.
    """

    name: str
    description: str
    handler: Callable[..., Awaitable[dict[str, object]]]


class AgentRuntime(ABC):
    """Run and control one native agent for a workflow runner.

    Implementations bind configuration, tools, and native conversation references
    during construction, then acquire execution resources in start(). The native
    harness remains responsible for authentication and conversation storage.
    """

    harness_name: ClassVar[str]

    def __init__(
        self,
        harness_config: HarnessConfig,
        session_directory: Path,
        *,
        tool_mcp_host: ToolMcpHost,
        tools: Sequence[AgentTool] = (),
    ) -> None:
        """Bind execution settings, tools, and session storage without starting native resources."""
        self.harness_config = harness_config
        self._tool_mcp_host = tool_mcp_host
        self.tool_mcp = create_tool_mcp(tools) if tools else None
        self.harness_directory = session_directory / "harnesses" / self.harness_name
        self.pane_id: str | None = None

    @classmethod
    @abstractmethod
    async def ensure_installed(cls) -> Path:
        """Return the native CLI launcher, preparing a missing installation for startup callers."""
        ...

    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        tool_mcp_url: str | None = None,
    ) -> list[str]:
        """Build this runtime's native argv, including its optional per-invocation MCP endpoint."""
        mcp_args = self._tool_mcp_args(tool_mcp_url) if tool_mcp_url is not None else ()
        return [str(executable), *mcp_args, *arguments]

    @staticmethod
    @abstractmethod
    def _tool_mcp_args(url: str) -> list[str]:
        """Encode this agent's Streamable HTTP endpoint as native CLI arguments."""
        ...

    async def start(
        self,
        workspace_id: str,
        *,
        terminal_session_name: str,
        workgroup_name: str,
        agent_name: str,
        is_entry: bool = False,
        system_prompt: str | None = None,
    ) -> None:
        """Bind the agent's pane and navigation identity, then start or attach the native CLI."""
        tokens = {"fore_rsi_group": workgroup_name, "fore_rsi_member": agent_name}
        if workgroup_name == WorkflowConfig.GLOBAL_WORKGROUP_NAME:
            tokens["fore_rsi_group_order"] = "0"
        elif is_entry:
            raise ValueError("The workflow entry agent must belong to the global workgroup.")
        # Encode the two name components separately: a slash in either name is not a group separator.
        pane = await ensure_terminal_pane(
            terminal_session_name,
            key=f"fore-rsi.agent/{quote(workgroup_name, safe='')}/{quote(agent_name, safe='')}",
            workspace_id=workspace_id,
            working_directory=Path.cwd(),
            label=f"{workgroup_name}/{agent_name}",
            tokens=tokens,
        )
        if is_entry:
            # Replacing one reference changes the entry without renaming or moving either member.
            await report_terminal_metadata(
                terminal_session_name,
                "workspace",
                workspace_id,
                {"fore_rsi_entry": pane["terminal_id"]},
            )
        self.pane_id = pane["pane_id"]
        executable = await self.ensure_installed()
        try:
            url = await self._tool_mcp_host.publish(self.tool_mcp)
            command = self.build_launch_command(executable, tool_mcp_url=url)
            await self._start_or_attach_cli(
                terminal_session_name, self.pane_id, command=command, system_prompt=system_prompt
            )
        except BaseException:
            await self._tool_mcp_host.unpublish(self.tool_mcp)
            raise

    @abstractmethod
    async def _start_or_attach_cli(
        self,
        terminal_session_name: str,
        pane_id: str,
        *,
        command: Sequence[str],
        system_prompt: str | None,
    ) -> None:
        """Start or resume with the prepared native argv, or attach to a CLI using the same endpoint.

        Preserve the harness's instructions when no system prompt is supplied.
        Return on readiness, not task completion.
        """
        ...

    @abstractmethod
    async def send_message(self, message: str) -> None:
        """Submit text through the native harness input and return after submission."""
        ...

    @abstractmethod
    async def wait_until_idle(self) -> None:
        """Wait for active execution and queued or automatic continuation to settle."""
        ...

    @abstractmethod
    async def inspect(self) -> dict[str, object]:
        """Return the native conversation reference, effective configuration, and execution state.

        Inspecting the runtime does not start or interrupt execution.
        """
        ...

    @abstractmethod
    def events(self) -> AsyncIterator[dict[str, object]]:
        """Observe native events, including output, tool activity, completion, and errors.

        Consuming events does not start execution; stopping observation does not
        interrupt the agent.
        """
        ...

    @abstractmethod
    async def fork(self) -> "AgentRuntime":
        """Create an independent runtime inheriting this conversation's recorded history.

        Leave the source runtime unchanged. The new runtime acquires execution
        resources through its own start().
        """
        ...

    @abstractmethod
    async def interrupt(self) -> None:
        """Request interruption of current work while keeping the conversation available."""
        ...

    async def close(self) -> None:
        """Stop this agent and remove its tool endpoint, preserving the native conversation."""
        try:
            await self._close_cli()
        finally:
            await self._tool_mcp_host.unpublish(self.tool_mcp)

    @abstractmethod
    async def _close_cli(self) -> None:
        """Release native resources; safe before startup, after failure, and after an earlier close."""
        ...
