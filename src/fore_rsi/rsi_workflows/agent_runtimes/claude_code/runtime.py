# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Claude Code CLI preparation and runtime contract."""

import json
import os
from pathlib import Path

from fore_rsi.config import ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base import MessageDeliveryMode
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed
from fore_rsi.rsi_workflows.agent_runtimes.named_conversation import NamedConversationRuntime


class ClaudeCodeAgentRuntime(NamedConversationRuntime):
    """Run Claude Code using its usual settings and an explicit member conversation UUID."""

    harness_name = "claude"

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Report the missing local Claude Code queue and steering API explicitly."""
        raise NotImplementedError(
            f"Claude Code has no documented native local {mode} message API for this runtime."
        )

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Claude Code's launcher for startup callers, using its native installer when missing."""
        return await ensure_cli_installed(
            cls.harness_name,
            Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude"),
            "https://claude.ai/install.ps1" if os.name == "nt" else "https://claude.ai/install.sh",
            shell="bash",
        )

    def effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Set the reasoning level for this Claude Code invocation."""
        return ["--effort", effort]

    def native_home(self) -> Path:
        """Use the user's Claude Code settings and credential store without copying them."""
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser().resolve()

    def tool_mcp_args(self) -> list[str]:
        """Add this member's tool client without replacing other configured MCP servers."""
        config = {"mcpServers": {"fore_rsi": self.stdio_server()}}
        return [f"--mcp-config={json.dumps(config)}"]
