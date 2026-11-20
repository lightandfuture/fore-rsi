# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Publish an agent's bound tools through the shared MCP implementation."""

from collections.abc import Awaitable, Callable, Sequence

from mcp.server import MCPServer


type AgentTool = Callable[..., Awaitable[dict[str, object]]]


def create_tool_mcp(tools: Sequence[AgentTool]) -> MCPServer:
    """Register the role's selected callables; MCP derives each tool's name, description and schema."""
    server = MCPServer("fore-rsi")
    for tool in tools:
        server.add_tool(tool, structured_output=True)
    return server
