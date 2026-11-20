# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common lifecycle and input operations for one native agent conversation."""

from abc import ABC, abstractmethod
import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

from fore_rsi.config import AgentConfig, WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool, create_tool_mcp
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost
from fore_rsi.utils.terminal import PaneLocation, ensure_terminal_pane, report_terminal_metadata, run_terminal


@dataclass(frozen=True)
class _PendingInput:
    sequence: int
    interrupted: bool = False

    def settled(self, agent: dict[str, object]) -> bool:
        if agent.get("agent_status") not in {"idle", "done"}:
            return False
        field = "state_change_seq" if self.interrupted else "completion_seq"
        return int(agent.get(field) or 0) > self.sequence


class AgentRuntime(ABC):
    """Run and control one native agent for a workflow runner.

    Implementations bind configuration, tools, and native conversation references
    during construction, then acquire execution resources in start(). The native
    harness owns authentication and conversation storage. Inspection, event
    streaming, and forking are optional; unsupported operations raise NotImplementedError.
    """

    harness_name: ClassVar[str]

    def __init__(
        self,
        agent_config: AgentConfig,
        session_directory: Path,
        *,
        workgroup_name: str,
        agent_name: str,
        tool_mcp_host: ToolMcpHost,
        tools: Sequence[AgentTool] = (),
    ) -> None:
        """Bind member identity, tools and storage without starting native resources."""
        self.workgroup_name = workgroup_name
        self.agent_name = agent_name
        self._pane_key = f"fore-rsi.agent/{quote(workgroup_name, safe='')}/{quote(agent_name, safe='')}"
        self.terminal_session_name = session_directory.name
        self.session_directory = session_directory
        self.terminal_id: str | None = None
        self.agent_config = agent_config
        self._tool_mcp_host = tool_mcp_host
        self._tools = tuple(tools)
        self.tool_mcp = create_tool_mcp(self._tools) if self._tools else None
        self.harness_directory = session_directory / "harnesses" / self.harness_name
        self.pane_id: str | None = None
        self._lifecycle = asyncio.Lock()
        self._input = asyncio.Lock()
        self._pending: _PendingInput | None = None
        self._failed_claim: str | None = None

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
        mcp_args = self._tool_mcp_args() if self.tool_mcp is not None else ()
        return [str(executable), *mcp_args, *arguments]

    @abstractmethod
    def _tool_mcp_args(self) -> list[str]:
        """Return native CLI arguments for connecting to this member's tools via its address file."""
        ...

    async def start(
        self,
        workspace_id: str,
        *,
        is_entry: bool = False,
        system_prompt: str | None = None,
    ) -> None:
        """Bind the agent's pane and navigation identity, then start or attach the native CLI."""
        if is_entry and self.workgroup_name != WorkflowConfig.GLOBAL_WORKGROUP_NAME:
            raise ValueError("The workflow entry agent must belong to the global workgroup.")
        async with self._lifecycle:
            if self.terminal_id is not None:
                raise RuntimeError("This runtime already controls a terminal.")
            await self._remove_failed_claim()
            executable = await self.ensure_installed()
            created: list[str] = []
            try:
                await self._tool_mcp_host.publish(self.tool_mcp, address_file=self.tool_address_file)
                command = self.build_launch_command(executable, system_prompt=system_prompt)
                # The terminal can allocate a pane before the launcher acknowledges it.
                # Let the shielded claim record that ownership before rolling back.
                claim = asyncio.create_task(self._claim_pane(workspace_id, command, is_entry, created))
                try:
                    pane, agent = await asyncio.shield(claim)
                except asyncio.CancelledError as cancellation:
                    try:
                        await claim
                    except Exception as error:
                        cancellation.add_note(f"Terminal claim also failed: {error}")
                    raise
                await self._wait_for_cli(pane, agent)
            except BaseException as error:
                try:
                    if created:
                        self._failed_claim = created[0]
                        await self._remove_failed_claim()
                except Exception as cleanup_error:
                    error.add_note(f"Terminal rollback failed: {cleanup_error}")
                finally:
                    self.pane_id = self.terminal_id = None
                    try:
                        await self._tool_mcp_host.unpublish(self.tool_mcp)
                    except Exception as cleanup_error:
                        error.add_note(f"Tool rollback failed: {cleanup_error}")
                raise

    async def _remove_failed_claim(self) -> None:
        if self._failed_claim is not None:
            await run_terminal(
                ["pane", "remove", "--key", self._pane_key, "--terminal-id", self._failed_claim],
                self.terminal_session_name, capture_output=True,
            )
            self._failed_claim = None

    def _member_file(self, suffix: str) -> Path:
        """Keep group and member names distinct even on case-insensitive filesystems."""
        group = self.workgroup_name.encode().hex()
        member = self.agent_name.encode().hex()
        return self.harness_directory / f"member-{group}-{member}{suffix}"

    @property
    def tool_address_file(self) -> Path:
        """Return the stable discovery file for the member's current tool endpoint."""
        return self._member_file(".mcp-url")

    async def _claim_pane(
        self, workspace_id: str, command: Sequence[str], is_entry: bool, created: list[str]
    ) -> tuple[PaneLocation, dict[str, object]]:
        """Acquire the exact keyed command without waiting for native startup or sign-in."""
        session = self.terminal_session_name
        tokens = {"fore_rsi_group": self.workgroup_name, "fore_rsi_member": self.agent_name}
        if self.workgroup_name == WorkflowConfig.GLOBAL_WORKGROUP_NAME:
            tokens["fore_rsi_group_order"] = "0"
        pane = await ensure_terminal_pane(
            session, key=self._pane_key, working_directory=Path.cwd(), workspace_id=workspace_id,
            command=command, label=f"{self.workgroup_name}/{self.agent_name}",
        )
        target = pane["terminal_id"]
        if pane.get("created"):
            created.append(target)
        result = await run_terminal(
            ["agent", "start", target, "--kind", self.harness_name, "--pane", pane["pane_id"],
             "--managed-executable", command[0], "--no-wait", "--", *command[1:]],
            session, capture_output=True,
        )
        self.pane_id, self.terminal_id = pane["pane_id"], target
        await report_terminal_metadata(session, "pane", self.pane_id, tokens)
        if is_entry:
            await report_terminal_metadata(session, "workspace", pane["workspace_id"], {"fore_rsi_entry": target})
        return pane, json.loads(result.stdout)["result"]["agent"]

    async def _wait_for_cli(self, pane: PaneLocation, agent: dict[str, object]) -> dict[str, object]:
        """Wait for the claimed editor; a native sign-in dialog remains cancellable."""
        target = pane["terminal_id"]
        while True:
            if (agent["terminal_id"], agent.get("name"), agent.get("agent")) != (target, target, self.harness_name):
                raise RuntimeError(f"{self.harness_name} no longer owns pane {pane['pane_id']}.")
            if agent.get("interactive_ready") and agent["agent_status"] != "blocked":
                return agent
            if agent["agent_status"] == "blocked":
                args = ["agent", "wait", target, "--until", "idle", "--until", "done", "--until", "working", "--until", "unknown"]
            else:
                await asyncio.sleep(0.1)
                args = ["agent", "get", target]
            result = await run_terminal(args, self.terminal_session_name, capture_output=True)
            agent = json.loads(result.stdout)["result"]["agent"]

    async def send_message(self, message: str) -> None:
        """Submit text to the recognized native editor, never to an unbound shell."""
        async with self._input:
            if self._pending is not None:
                agent = await self._bound_agent()
                if agent is None or not self._pending.settled(agent):
                    raise RuntimeError("The previous input has not settled. Wait before submitting again.")
                self._pending = None
            target = self._target()
            send = asyncio.create_task(run_terminal(
                ["agent", "prompt", "--require-idle", "--", target, message],
                self.terminal_session_name, capture_output=True,
            ))
            try:
                result = await asyncio.shield(send)
            except asyncio.CancelledError as cancellation:
                try:
                    result = await send
                    self._record_submission(result.stdout)
                except Exception as error:
                    cancellation.add_note(f"Prompt acknowledgement also failed: {error}")
                raise
            self._record_submission(result.stdout)

    def _record_submission(self, response: str) -> None:
        agent = json.loads(response)["result"]["agent"]
        self._pending = _PendingInput(agent["state_change_seq"])

    async def wait_until_idle(self) -> None:
        """Wait for settlement after the most recent acknowledged input."""
        stale_since: float | None = None
        while True:
            async with self._input:
                pending = self._pending
                if pending is None:
                    target = self._target()
                    break
                agent = await self._bound_agent()
                if agent is None:
                    raise RuntimeError("The bound agent has exited.")
                if pending.settled(agent):
                    self._pending = None
                    return
                if agent["agent_status"] in {"working", "blocked"}:
                    stale_since = None
                else:
                    now = asyncio.get_running_loop().time()
                    stale_since = now if stale_since is None else stale_since
                    if now - stale_since >= 5:
                        raise RuntimeError("The terminal has not confirmed settlement of the submitted input.")
            await asyncio.sleep(WorkflowConfig.STOP_POLL_INTERVAL_SECONDS)
        await run_terminal(
            ["agent", "wait", target, "--until", "idle", "--until", "done"],
            self.terminal_session_name, capture_output=True,
        )

    async def inspect(self) -> dict[str, object]:
        """Return the native conversation reference, effective configuration, and execution state.

        Inspecting the runtime does not start or interrupt execution.
        """
        raise NotImplementedError(f"The {self.harness_name!r} harness does not support conversation inspection.")

    def events(self) -> AsyncIterator[dict[str, object]]:
        """Observe native events, including output, tool activity, completion, and errors.

        Consuming events does not start execution; stopping observation does not
        interrupt the agent.
        """
        raise NotImplementedError(f"The {self.harness_name!r} harness does not support native event streaming.")

    async def fork(self) -> "AgentRuntime":
        """Create an independent runtime inheriting this conversation's recorded history.

        Leave the source runtime unchanged. The new runtime acquires execution
        resources through its own start().
        """
        raise NotImplementedError(f"The {self.harness_name!r} harness does not support conversation forks.")

    async def interrupt(self) -> None:
        """Interrupt the foreground turn without closing the native conversation."""
        async with self._input:
            agent = await self._bound_agent()
            if agent is None:
                raise RuntimeError("The bound agent has exited.")
            if agent["agent_status"] in {"idle", "done"} and (
                self._pending is None or self._pending.settled(agent)
            ):
                self._pending = None
                return
            await run_terminal(
                ["agent", "send-keys", self._target(), "esc"], self.terminal_session_name, capture_output=True,
            )
            self._pending = _PendingInput(agent["state_change_seq"], interrupted=True)

    async def close(self) -> None:
        """Stop this agent and remove its tool endpoint, preserving the native conversation."""
        async with self._lifecycle, self._input:
            try:
                await self._remove_failed_claim()
                await self._close_cli()
                self.pane_id = self.terminal_id = None
                self._pending = None
            finally:
                await self._tool_mcp_host.unpublish(self.tool_mcp)

    async def _close_cli(self) -> None:
        """Quit only the bound editor without submitting any draft already in its input buffer."""
        if await self._bound_agent() is None:
            return
        await run_terminal(
            ["agent", "send-keys", self._target(), "ctrl+c", "ctrl+c"],
            self.terminal_session_name, capture_output=True,
        )
        async with asyncio.timeout(30):
            while await self._bound_agent() is not None:
                await asyncio.sleep(WorkflowConfig.STOP_POLL_INTERVAL_SECONDS)

    async def _bound_agent(self) -> dict | None:
        """Return the live terminal record only while the bound identity, alias and native editor still match."""
        if self.terminal_id is None:
            return None
        result = await run_terminal(["agent", "list"], self.terminal_session_name, capture_output=True)
        for agent in json.loads(result.stdout)["result"]["agents"]:
            if agent["terminal_id"] == self.terminal_id == agent.get("name") and agent.get("agent") == self.harness_name:
                return agent
        return None

    def _target(self) -> str:
        """Use the terminal identity as a live alias so input follows a moved agent."""
        if self.terminal_id is None:
            raise RuntimeError(f"The {self.harness_name} agent has not been started in a terminal.")
        return self.terminal_id
