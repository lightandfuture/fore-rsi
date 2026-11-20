# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Agent execution backend selection and runtime construction."""

from collections.abc import Sequence
from inspect import isabstract
from pathlib import Path

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.claude_code import ClaudeCodeAgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.codex import CodexAgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.pi import PiAgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost


def create_agent_runtime(
    agent_config: AgentConfig,
    session_directory: Path,
    *,
    workgroup_name: str,
    agent_name: str,
    tool_mcp_host: ToolMcpHost,
    tools: Sequence[AgentTool] = (),
) -> AgentRuntime:
    """Construct the selected runtime for one workflow member without opening its pane."""
    runtime_class = get_agent_runtime_class(agent_config.harness)
    return runtime_class(
        agent_config, session_directory,
        workgroup_name=workgroup_name, agent_name=agent_name, tool_mcp_host=tool_mcp_host, tools=tools,
    )


def get_agent_runtime_class(harness_name: str) -> type[AgentRuntime]:
    """Return a backend that can launch interactive agents, or name the available choices."""
    runtimes = (PiAgentRuntime, CodexAgentRuntime, ClaudeCodeAgentRuntime)
    selected = next((runtime for runtime in runtimes if runtime.harness_name == harness_name), None)
    if selected is not None and not isabstract(selected):
        return selected

    available = ", ".join(runtime.harness_name for runtime in runtimes if not isabstract(runtime))
    reason = f"Unknown harness {harness_name!r}" if selected is None else f"Harness {harness_name!r} cannot launch agents yet"
    raise ValueError(f"{reason}. Available harnesses: {available}.")
