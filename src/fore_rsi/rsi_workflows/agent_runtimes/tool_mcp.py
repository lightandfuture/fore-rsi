# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Publish an agent's bound tools through the shared MCP implementation."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from mcp.server import MCPServer

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.agent_runtimes.base import AgentTool


def create_tool_mcp(tools: Sequence["AgentTool"]) -> MCPServer:
    """Build a runtime's MCP tool service without opening a transport.

    Explicitly registered handlers define the public tool arguments and results.
    The runtime owns the service's eventual transport and shutdown.
    """
    server = MCPServer("fore-rsi")
    for tool in tools:
        server.add_tool(
            tool.handler,
            name=tool.name,
            description=tool.description,
            structured_output=True,
        )
    return server
