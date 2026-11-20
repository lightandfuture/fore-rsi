# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Codex CLI preparation and runtime contract."""

import json
import os
from pathlib import Path

from fore_rsi.config import Config, ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed
from fore_rsi.rsi_workflows.agent_runtimes.named_conversation import NamedConversationRuntime
from fore_rsi.rsi_workflows.agent_runtimes.native_launch import codex_profiles, codex_thread


class CodexAgentRuntime(NamedConversationRuntime):
    """Open Codex in a workflow pane and retain each member's native thread separately."""

    harness_name = "codex"

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
        """Release the PTY and retain the UUID once Codex has flushed its first durable turn."""
        was_bound = self.terminal_id is not None
        await super().close()
        if was_bound:
            member = self._member_file("")
            codex_thread(member.with_suffix(".id"), self.harness_directory / "sessions" / member.name)

    def _effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Override this invocation's reasoning effort without editing Codex's profile."""
        return ["-c", f"model_reasoning_effort={json.dumps(effort)}"]

    def _native_home(self) -> Path:
        """Keep Codex profile and sign-in state outside the project containing workflow transcripts."""
        return codex_profiles(Config.SESSION_INDEX_PATH.parent, self.terminal_session_name) / self._member_file("").name

    def _tool_mcp_args(self) -> list[str]:
        """Configure the member's stdio MCP client for this invocation without editing config.toml."""
        options = []
        for key, value in self._stdio_server().items():
            options.extend(["-c", f"mcp_servers.fore_rsi.{key}={json.dumps(value, ensure_ascii=False)}"])
        return options
