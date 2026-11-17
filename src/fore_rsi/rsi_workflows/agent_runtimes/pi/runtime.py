# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Pi CLI preparation and runtime contract."""

from collections.abc import Sequence
import os
from pathlib import Path

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed


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
        tool_mcp_url: str | None = None,
    ) -> list[str]:
        """Use this workflow session's Pi directory for new conversations and ID-based resume."""
        return super().build_launch_command(
            executable,
            ["--session-dir", str(self.harness_directory), *arguments],
            tool_mcp_url=tool_mcp_url,
        )

    @staticmethod
    def _tool_mcp_args(url: str) -> list[str]:
        """Load the bundled Pi extension with this session's tool endpoint."""
        extension = Path(__file__).resolve().with_name("tool_mcp.ts")
        return ["--extension", str(extension), "--fore-rsi-mcp-url", url]
