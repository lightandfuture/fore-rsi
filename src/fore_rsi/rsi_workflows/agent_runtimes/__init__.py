# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Agent execution backend selection and runtime construction."""

from collections.abc import Sequence
from pathlib import Path

from fore_rsi.config import HarnessConfig
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime, AgentTool
from fore_rsi.rsi_workflows.agent_runtimes.claude_code import ClaudeCodeAgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.codex import CodexAgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.pi import PiAgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost


def create_agent_runtime(
    harness_config: HarnessConfig,
    session_directory: Path,
    *,
    tool_mcp_host: ToolMcpHost,
    tools: Sequence[AgentTool] = (),
) -> AgentRuntime:
    """Construct an unstarted runtime with the owning workflow session's root directory."""
    pass


def get_agent_runtime_class(harness_name: str) -> type[AgentRuntime]:
    """Select a backend's runtime class for CLI validation and agent construction."""
    runtime_classes = (PiAgentRuntime, CodexAgentRuntime, ClaudeCodeAgentRuntime)
    for runtime_class in runtime_classes:
        if runtime_class.harness_name == harness_name:
            return runtime_class

    available = ", ".join(runtime_class.harness_name for runtime_class in runtime_classes)
    raise ValueError(f"Unknown harness {harness_name!r}. Available harnesses: {available}.")
