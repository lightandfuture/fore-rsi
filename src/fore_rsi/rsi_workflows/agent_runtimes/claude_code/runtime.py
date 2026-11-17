# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Claude Code CLI preparation and runtime contract."""

import json
import os
from pathlib import Path

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed


class ClaudeCodeAgentRuntime(AgentRuntime):
    """Runtime contract for Claude Code's native CLI."""

    harness_name = "claude"

    @classmethod
    async def ensure_installed(cls) -> Path:
        """Return Claude Code's launcher for startup callers, using its native installer when missing."""
        return await ensure_cli_installed(
            cls.harness_name,
            Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude"),
            "https://claude.ai/install.ps1" if os.name == "nt" else "https://claude.ai/install.sh",
            shell="bash",
        )

    @staticmethod
    def _tool_mcp_args(url: str) -> list[str]:
        """Add the tool endpoint using Claude Code's per-invocation MCP configuration."""
        config = {"mcpServers": {"fore_rsi": {"type": "http", "url": url}}}
        return [f"--mcp-config={json.dumps(config)}"]
