# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run one workflow member in the native Pi terminal with its own conversation and tools."""

import asyncio
from collections.abc import Sequence
import json
import os
from pathlib import Path
import secrets
import socket
from uuid import uuid4

import httpx2

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime, MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed
from fore_rsi.rsi_workflows.agent_runtimes.pi.conversation import (
    IpcEndpoint, PiObservation, recorded_observation,
)
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost
from fore_rsi.utils.paths import write_private_text
from fore_rsi.utils.terminal import PaneLocation, run_terminal, terminal_executable


class PiAgentRuntime(AgentRuntime):
    """Runtime contract for Pi's native CLI."""

    harness_name = "pi"

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
        """Create a Pi runtime with an in-memory IPC address shared with its extension."""
        super().__init__(
            agent_config,
            workflow_directory,
            workgroup_name=workgroup_name,
            agent_name=agent_name,
            tool_mcp_host=tool_mcp_host,
            tools=tools,
        )
        self.ipc_endpoint = self.create_ipc_endpoint()

    def create_ipc_endpoint(self) -> IpcEndpoint:
        """Choose a private local socket, using a reserved TCP port on Windows."""
        endpoint: IpcEndpoint = {"token": secrets.token_urlsafe(32)}
        if os.name == "nt":
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                endpoint["port"] = listener.getsockname()[1]
        else:
            endpoint["socket_path"] = f"/tmp/fore-rsi-{uuid4().hex}.sock"
        return endpoint

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Pi's launcher for startup callers, using the official installer when missing."""
        agent_directory = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
        return await ensure_cli_installed(
            cls.harness_name,
            agent_directory / "bin" / ("pi.cmd" if os.name == "nt" else "pi"),
            "https://pi.dev/install.ps1" if os.name == "nt" else "https://pi.dev/install.sh",
        )

    def build_launch_command(
        self,
        executable: Path,
        arguments: Sequence[str] = (),
        *,
        system_prompt: str | None = None,
    ) -> list[str]:
        """Open this member's transcript with Pi's native lifecycle hook, role instructions and tools."""
        self.harness_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Pi deduplicates extensions by path. Reuse the terminal hook if the user already installed it.
        profile = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi" / "agent").expanduser()
        hook = profile / "extensions" / "herdr-agent-state.ts"
        integrations = terminal_executable().parent
        if not hook.is_file():
            hook = integrations / hook.name
        native = ["--extension", str(integrations / "observation.ts")]
        if "socket_path" in self.ipc_endpoint:
            native.extend(["--fore-rsi-observation-socket", self.ipc_endpoint["socket_path"]])
        else:
            native.extend(["--fore-rsi-observation-port", str(self.ipc_endpoint["port"])])
        native.extend([
            "--fore-rsi-observation-token", self.ipc_endpoint["token"],
            "--extension", str(hook), "--session-dir", str(self.harness_directory),
            "--session", str(self.get_agent_file_path(".jsonl")),
        ])
        if self.agent_config.model is not None:
            native.extend(["--model", self.agent_config.model])
        if self.agent_config.effort is not None:
            native.extend(["--thinking", self.agent_config.effort])
        instructions = self.get_agent_file_path(".instructions.md")
        if system_prompt is not None:
            write_private_text(instructions, system_prompt)
        if instructions.is_file():
            native.extend(["--append-system-prompt", str(instructions)])
        return super().build_launch_command(executable, [*native, *arguments])

    async def close(self) -> None:
        """Stop Pi and remove a private Unix socket left by an interrupted native process."""
        try:
            await super().close()
        finally:
            socket_path = self.ipc_endpoint.get("socket_path")
            if socket_path:
                Path(socket_path).unlink(missing_ok=True)

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Deliver a user message through Pi's native steer or follow-up queue."""
        async with self.message_lock:
            _, state = await self.observation()
            if state == "stopped":
                raise RuntimeError("Start the Pi member before sending a native message.")
            async with self.observer_client() as client:
                response = await client.post(
                    "/message",
                    json={"message": message, "mode": mode},
                )
                response.raise_for_status()

    def observer_client(self) -> httpx2.AsyncClient:
        """Connect to the member's private local IPC endpoint without using workstation proxies."""
        transport = None
        base_url = "http://127.0.0.1"
        if "socket_path" in self.ipc_endpoint:
            transport = httpx2.AsyncHTTPTransport(uds=self.ipc_endpoint["socket_path"])
            base_url = "http://pi"
        else:
            base_url = f"http://127.0.0.1:{self.ipc_endpoint['port']}"
        return httpx2.AsyncClient(
            base_url=base_url,
            transport=transport,
            trust_env=False,
            headers={"Authorization": f"Bearer {self.ipc_endpoint['token']}"},
        )

    async def live_observation(self) -> PiObservation:
        """Read live session settings directly from the Pi extension over local IPC."""
        async with self.observer_client() as client:
            response = await client.get("/state")
            response.raise_for_status()
            return response.json()

    async def observation(self) -> tuple[PiObservation, str]:
        """Pair Pi's live session settings with its bound terminal owner."""
        agent = await self.get_agent()
        if agent is None:
            info = await asyncio.to_thread(recorded_observation, self.get_agent_file_path(".jsonl"))
            return info, "stopped"
        info = await self.live_observation()
        session = agent.get("agent_session")
        if session and (session["kind"] != "path"
                        or Path(session["value"]).resolve() != Path(info["session_file"]).resolve()):
            raise RuntimeError("Pi is no longer observing the conversation reported by its terminal.")
        return info, agent["agent_status"]

    async def wait_for_agent_ready(self, pane: PaneLocation, agent: dict[str, object]) -> dict[str, object]:
        """Confirm Pi's record file and IPC endpoint after the terminal reports readiness."""
        agent = await super().wait_for_agent_ready(pane, agent)
        expected_file = self.get_agent_file_path(".jsonl").resolve()
        agent_session = agent.get("agent_session")
        if not isinstance(agent_session, dict) or agent_session.get("kind") != "path":
            raise RuntimeError(f"Pi in pane {pane['pane_id']} did not report its record file.")
        if Path(agent_session["value"]).resolve() != expected_file:
            raise RuntimeError(f"Pi in pane {pane['pane_id']} is using another record file.")
        info = await self.live_observation()
        if Path(info["session_file"]).resolve() != expected_file:
            raise RuntimeError(f"Pi in pane {pane['pane_id']} reported another record file.")
        return agent

    def tool_mcp_args(self) -> list[str]:
        """Pass the discovery file, not a host-specific capability, in the replayable argv."""
        extension = terminal_executable().with_name("tool_mcp.ts")
        return ["--extension", str(extension), "--fore-rsi-mcp-file", str(self.get_agent_file_path(".mcp-url"))]
