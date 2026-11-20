# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common lifecycle and input operations for one native agent conversation."""

import asyncio
import json
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import quote

from fore_rsi.config import AgentConfig, WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import (
    AgentTool,
    ToolMcpHost,
    create_tool_mcp,
)
from fore_rsi.utils.terminal import (
    PaneLocation,
    ensure_terminal_pane,
    report_terminal_metadata,
    run_terminal,
    terminal_executable,
)

type MessageDeliveryMode = Literal["queue", "steer"]


class AgentRuntime(ABC):
    """Run and control one native agent for a workflow runner.

    Implementations bind configuration, tools, and native conversation references
    during construction, then acquire execution resources in start(). The native
    harness owns authentication and conversation storage.
    """

    harness_name: ClassVar[str]

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
        """Bind member identity, tools and storage without starting native resources."""
        self.workgroup_name = workgroup_name
        self.agent_name = agent_name
        self.pane_key = f"fore-rsi.agent/{quote(workgroup_name, safe='')}/{quote(agent_name, safe='')}"
        self.terminal_session_name = workflow_directory.name
        self.workflow_directory = workflow_directory
        self.terminal_id: str | None = None
        self.agent_config = agent_config
        self.tool_mcp_host = tool_mcp_host
        self.tools = tuple(tools)
        self.tool_mcp = create_tool_mcp(self.tools) if self.tools else None
        self.harness_directory = workflow_directory / "harnesses" / self.harness_name
        self.pane_id: str | None = None
        self.message_lock = asyncio.Lock()
        self.lifecycle = asyncio.Lock()
        self.failed_pane_id: str | None = None

    async def start(
        self,
        workspace_id: str,
        *,
        is_entry: bool = False,
        system_prompt: str | None = None,
    ) -> None:
        """Bind the agent's pane and navigation identity, then start or attach the native CLI."""
        async with self.lifecycle:
            if self.terminal_id is not None:
                raise RuntimeError("This runtime already controls a terminal.")
            await self.remove_failed_pane()
            executable = await self.ensure_installed()
            try:
                await self.tool_mcp_host.publish(
                    self.tool_mcp,
                    address_file=self.get_agent_file_path(".mcp-url"),
                )
                command = self.build_launch_command(executable, system_prompt=system_prompt)

                async def launch_agent() -> tuple[PaneLocation, dict[str, object]]:
                    pane = await self.get_pane(workspace_id, command)
                    agent = await self.start_agent_in_pane(pane, command, is_entry)
                    return pane, agent

                claim = asyncio.create_task(launch_agent())
                try:
                    pane, agent = await asyncio.shield(claim)
                except asyncio.CancelledError as cancellation:
                    try:
                        await claim
                    except Exception as error:
                        cancellation.add_note(f"Agent launch also failed: {error}")
                    raise
                await self.wait_for_agent_ready(pane, agent)
                self.failed_pane_id = None
            except BaseException as error:
                try:
                    if self.terminal_id is not None:
                        await self.stop_agent_runtime()
                except Exception as cleanup_error:
                    error.add_note(f"Agent rollback failed: {cleanup_error}")
                try:
                    await self.remove_failed_pane()
                except Exception as cleanup_error:
                    error.add_note(f"Pane rollback failed: {cleanup_error}")
                finally:
                    self.pane_id = self.terminal_id = None
                    try:
                        await self.tool_mcp_host.unpublish(self.tool_mcp)
                    except Exception as cleanup_error:
                        error.add_note(f"Tool rollback failed: {cleanup_error}")
                raise

    @abstractmethod
    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Deliver a prompt through the harness's native queue or steering interface."""
        ...

    async def close(self) -> None:
        """Stop this agent and remove its tool endpoint, preserving the native conversation."""
        async with self.lifecycle, self.message_lock:
            try:
                await self.remove_failed_pane()
                await self.stop_agent_runtime()
                self.pane_id = self.terminal_id = None
            finally:
                await self.tool_mcp_host.unpublish(self.tool_mcp)

    @classmethod
    def remove_workflow_storage(cls, workflow_directory: Path) -> None:
        """Remove native links that still refer to a deleted workflow directory."""

    def launch_environment(self) -> Mapping[str, str]:
        """Return environment variables that the terminal must preserve for this native process."""
        return {}

    def tool_stdio_server(self) -> dict[str, object]:
        """Describe the isolated stdio bridge that forwards this member's MCP requests."""
        bridge = terminal_executable().with_name("tool_stdio.py")
        return {
            "command": sys.executable,
            "args": ["-I", "-S", str(bridge), str(self.get_agent_file_path(".mcp-url"))],
        }

    @classmethod
    @abstractmethod
    async def ensure_installed(cls) -> Path:
        """Return the native CLI launcher, preparing a missing installation for startup callers."""
        ...

    @abstractmethod
    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        system_prompt: str | None = None,
    ) -> list[str]:
        """Prepare the member's replayable argv, including any role instructions and tools."""
        mcp_args = self.tool_mcp_args() if self.tool_mcp is not None else ()
        return [str(executable), *mcp_args, *arguments]

    @abstractmethod
    def tool_mcp_args(self) -> list[str]:
        """Return native CLI arguments for connecting to this member's tools via its address file."""
        ...

    async def remove_failed_pane(self) -> None:
        """Remove a pane created by a startup attempt that did not complete."""
        if self.failed_pane_id is not None:
            await run_terminal(
                ["pane", "remove", "--key", self.pane_key, "--terminal-id", self.failed_pane_id],
                self.terminal_session_name, capture_output=True,
            )
            self.failed_pane_id = None

    def get_agent_file_path(self, suffix: str) -> Path:
        """Keep group and member names distinct even on case-insensitive filesystems."""
        group = self.workgroup_name.encode().hex()
        member = self.agent_name.encode().hex()
        return self.harness_directory / f"member-{group}-{member}{suffix}"

    async def get_pane(self, workspace_id: str, command: Sequence[str]) -> PaneLocation:
        """Create or reuse the member's keyed terminal pane."""
        terminal_session_name = self.terminal_session_name
        pane_metadata = {"fore_rsi_group": self.workgroup_name, "fore_rsi_member": self.agent_name}
        if self.workgroup_name == WorkflowConfig.GLOBAL_WORKGROUP_NAME:
            pane_metadata["fore_rsi_group_order"] = "0"
        pane = await ensure_terminal_pane(
            terminal_session_name,
            key=self.pane_key,
            working_directory=Path.cwd(),
            workspace_id=workspace_id,
            command=command,
            label=f"{self.workgroup_name}/{self.agent_name}",
            tokens=pane_metadata,
            environment=self.launch_environment(),
        )
        if pane.get("created"):
            self.failed_pane_id = pane["terminal_id"]
        return pane

    async def start_agent_in_pane(
        self,
        pane: PaneLocation,
        command: Sequence[str],
        is_entry: bool,
    ) -> dict[str, object]:
        """Start the native CLI in a prepared pane and bind its Runtime identity."""
        terminal_session_name = self.terminal_session_name
        target = pane["terminal_id"]
        result = await run_terminal(
            ["agent", "start", target, "--kind", self.harness_name, "--pane", pane["pane_id"],
             "--managed-executable", command[0], "--no-wait", "--", *command[1:]],
            terminal_session_name,
            capture_output=True,
        )
        self.pane_id, self.terminal_id = pane["pane_id"], target
        if is_entry:
            await report_terminal_metadata(
                terminal_session_name,
                "workspace",
                pane["workspace_id"],
                {"fore_rsi_entry": target},
            )
        return json.loads(result.stdout)["result"]["agent"]

    async def wait_for_agent_ready(self, pane: PaneLocation, agent: dict[str, object]) -> dict[str, object]:
        """Wait for the terminal's readiness event before accepting native input."""
        target = pane["terminal_id"]
        result = await run_terminal(
            ["agent", "wait", target, "--until-ready", "--timeout", "30000"],
            self.terminal_session_name,
            capture_output=True,
        )
        agent = json.loads(result.stdout)["result"]["agent"]
        if (agent["terminal_id"], agent.get("name"), agent.get("agent")) != (target, target, self.harness_name):
            raise RuntimeError(f"{self.harness_name} no longer owns pane {pane['pane_id']}.")
        return agent

    async def stop_agent_runtime(self) -> None:
        """Quit the bound editor without submitting any draft already in its input buffer."""
        agent = await self.get_agent()
        if agent is None:
            return
        await run_terminal(
            ["agent", "send-keys", agent["terminal_id"], "ctrl+c", "ctrl+c"],
            self.terminal_session_name, capture_output=True,
        )
        await run_terminal(
            ["agent", "wait", agent["terminal_id"], "--until-stopped", "--timeout", "30000"],
            self.terminal_session_name,
            capture_output=True,
        )

    async def get_agent(self) -> dict | None:
        """Return the live terminal record only while the bound identity, alias and native editor still match."""
        if self.terminal_id is None:
            return None
        result = await run_terminal(["agent", "list"], self.terminal_session_name, capture_output=True)
        for agent in json.loads(result.stdout)["result"]["agents"]:
            if agent["terminal_id"] == self.terminal_id == agent.get("name") and agent.get("agent") == self.harness_name:
                return agent
        return None
