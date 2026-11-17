# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Codex CLI preparation and runtime contract."""

import json
import os
from pathlib import Path

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.installation import ensure_cli_installed


class CodexAgentRuntime(AgentRuntime):
    """Runtime contract for Codex's native CLI."""

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

    @staticmethod
    def _tool_mcp_args(url: str) -> list[str]:
        """Add the tool endpoint as a TOML override for this Codex invocation."""
        return ["-c", f"mcp_servers.fore_rsi.url={json.dumps(url, ensure_ascii=False)}"]
