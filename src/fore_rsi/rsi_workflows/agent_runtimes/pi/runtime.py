# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run one workflow member in the native Pi terminal with its own conversation and tools."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx2

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed
from fore_rsi.rsi_workflows.agent_runtimes.pi.conversation import (
    ObserverEndpoint, PiObservation, fork_recording, recorded_observation,
)
from fore_rsi.utils.paths import write_private_text
from fore_rsi.utils.terminal import PaneLocation, run_terminal, terminal_executable


class PiAgentRuntime(AgentRuntime):
    """Runtime contract for Pi's native CLI."""

    harness_name = "pi"

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
        native = [
            "--extension", str(integrations / "observation.ts"),
            "--fore-rsi-observation-file", str(self._member_file(".observation.json")),
            "--extension", str(hook), "--session-dir", str(self.harness_directory),
            "--session", str(self._member_file(".jsonl")),
        ]
        if self.agent_config.model is not None:
            native.extend(["--model", self.agent_config.model])
        if self.agent_config.effort is not None:
            native.extend(["--thinking", self.agent_config.effort])
        instructions = self._member_file(".instructions.md")
        if system_prompt is not None:
            write_private_text(instructions, system_prompt)
        if instructions.is_file():
            native.extend(["--append-system-prompt", str(instructions)])
        return super().build_launch_command(executable, [*native, *arguments])

    async def inspect(self) -> dict[str, object]:
        """Return Pi's session path, ID, selected model and effort, and the terminal's execution state.

        A stopped member reports its last observed or recorded selection; unobserved settings are None.
        """
        info, state = await self._observation()
        return {
            "session_file": info["session_file"], "session_id": info["session_id"],
            "model": info["model"], "effort": info["effort"], "state": state,
        }

    async def events(self) -> AsyncIterator[dict[str, object]]:
        """Subscribe to this running Pi. The first `subscribed` event marks the live, no-replay boundary.

        Subsequent events carry text deltas, tool start/end, model errors and final settlement.
        Closing the iterator releases only the observation connection.
        """
        info, state = await self._observation()
        endpoint = info.get("endpoint")
        if state == "stopped" or endpoint is None:
            raise RuntimeError("Start the Pi member before subscribing to its events.")
        async with self._observer_client(endpoint) as client:
            async with client.stream("GET", "/events", timeout=None) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    yield json.loads(line)

    async def fork(self) -> "PiAgentRuntime":
        """Fork a saved conversation at its active leaf; the independent member starts only on `start()`."""
        info, state = await self._observation()
        if state != "stopped" and (endpoint := info.get("endpoint")):
            async with self._observer_client(endpoint) as client:
                response = await client.get("/fork-point")
                response.raise_for_status()
                info = response.json()
        source = Path(info["session_file"]).resolve()
        if not source.is_file():
            raise FileNotFoundError("Pi has no saved conversation to fork. Send a message first.")
        config = replace(self.agent_config)
        # A live or cleanly closed editor reports its actual selection. Otherwise let Pi restore
        # recorded settings at startup rather than turning a past response into a model override.
        if "fork_point" in info:
            config.model, config.effort = info["model"], info["effort"]
        child = PiAgentRuntime(
            config, self.session_directory, workgroup_name=self.workgroup_name, agent_name=f"fork-{uuid4().hex}",
            tool_mcp_host=self._tool_mcp_host, tools=self._tools,
        )
        destination = child._member_file(".jsonl")
        await fork_recording(await self.ensure_installed(), source, destination, info.get("fork_point"))
        instructions = self._member_file(".instructions.md")
        try:
            if instructions.is_file():
                write_private_text(child._member_file(".instructions.md"), instructions.read_text(encoding="utf-8"))
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return child

    @staticmethod
    def _observer_client(endpoint: ObserverEndpoint) -> httpx2.AsyncClient:
        """Connect only to the member's local Pi process, independently of workstation proxy settings."""
        return httpx2.AsyncClient(
            base_url=f"http://127.0.0.1:{endpoint['port']}", trust_env=False,
            headers={"Authorization": f"Bearer {endpoint['token']}"},
        )

    def _reported_observation(self) -> PiObservation | None:
        """Read one atomic publication from the native editor, including before its first persisted turn."""
        try:
            return json.loads(self._member_file(".observation.json").read_bytes())
        except FileNotFoundError:
            return None

    async def _observation(self) -> tuple[PiObservation, str]:
        """Pair the native settings with their live terminal owner; a stale endpoint is never proof of execution."""
        agent = await self._bound_agent()
        info = self._reported_observation()
        if agent is None or info is None:
            path = Path(info["session_file"]) if info else self._member_file(".jsonl")
            info = await asyncio.to_thread(recorded_observation, path, info)
        if agent is None:
            return info, "stopped"
        session = agent.get("agent_session")
        if session and (session["kind"] != "path"
                        or Path(session["value"]).resolve() != Path(info["session_file"]).resolve()):
            raise RuntimeError("Pi is no longer observing the conversation reported by its terminal.")
        return info, agent["agent_status"]

    async def _wait_for_cli(self, pane: PaneLocation, agent: dict[str, object]) -> dict[str, object]:
        """Wait for Pi itself to report the member's open conversation before accepting input."""
        target = pane["terminal_id"]
        agent = await super()._wait_for_cli(pane, agent)
        expected_file = self._member_file(".jsonl").resolve()
        # A process or a saved layout can report idle before the native editor accepts input.
        async with asyncio.timeout(30):
            while True:
                if agent.get("screen_detection_skipped") and (session := agent.get("agent_session")):
                    if session["kind"] != "path" or Path(session["value"]).resolve() != expected_file:
                        raise RuntimeError(f"Pi in pane {pane['pane_id']} is using another conversation.")
                    info = self._reported_observation()
                    if info and info.get("endpoint") and Path(info["session_file"]).resolve() == expected_file:
                        return agent
                await asyncio.sleep(0.1)
                result = await run_terminal(["agent", "get", target], self.terminal_session_name, capture_output=True)
                agent = json.loads(result.stdout)["result"]["agent"]

    def _tool_mcp_args(self) -> list[str]:
        """Pass the discovery file, not a host-specific capability, in the replayable argv."""
        extension = terminal_executable().with_name("tool_mcp.ts")
        return ["--extension", str(extension), "--fore-rsi-mcp-file", str(self.tool_address_file)]
