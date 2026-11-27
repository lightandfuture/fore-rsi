# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Define Agent tools and serve each set through a workflow-owned MCP endpoint."""

import asyncio
from functools import partial, update_wrapper
from inspect import signature
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from secrets import token_urlsafe

import anyio
import uvicorn
from anyio.abc import TaskGroup, TaskStatus
from mcp.server import MCPServer
from starlette.routing import Mount, Router

from fore_rsi.utils.paths import write_private_text

type AgentTool = Callable[..., Awaitable[dict[str, object]]]


def register_agent_tool(
    tool: AgentTool,
    **dependencies: object,
) -> AgentTool:
    """Bind private Workflow dependencies before the tool is registered with MCP."""
    registered_tool = partial(tool, **dependencies)
    update_wrapper(registered_tool, tool)
    # MCP builds its input schema from the callable signature. Bound workflow
    # dependencies are not arguments a model can supply.
    public = signature(tool)
    registered_tool.__signature__ = public.replace(
        parameters=[p for p in public.parameters.values() if p.name not in dependencies]
    )
    return registered_tool


def create_tool_mcp(tools: Sequence[AgentTool]) -> MCPServer:
    """Register the tools selected for one Agent in an MCP server."""
    server = MCPServer("fore-rsi")
    for tool in tools:
        server.add_tool(tool, structured_output=True)
    return server


@dataclass
class ToolServerEndpoint:
    """One Agent's route and shutdown signals on the shared MCP listener."""

    url: str
    stop_event: anyio.Event = field(default_factory=anyio.Event)
    closed_event: anyio.Event = field(default_factory=anyio.Event)


class ToolMcpHost:
    """Keep each Agent's tool set reachable for its agent process."""

    def __init__(self) -> None:
        """Prepare an empty host; the first published tool set opens the listener."""
        self.mcp_router = Router()
        self.task_group: TaskGroup | None = None
        self.server_origin: str | None = None
        self.tool_endpoints: dict[MCPServer, ToolServerEndpoint] = {}
        self.host_lock = asyncio.Lock()

    @asynccontextmanager
    async def serve(self) -> AsyncIterator[None]:
        """Own the listener and all published endpoints until the workflow exits."""
        async with anyio.create_task_group() as task_group:
            self.task_group = task_group
            try:
                yield
            finally:
                self.task_group = None
                self.server_origin = None
                task_group.cancel_scope.cancel()

    async def publish(self, server: MCPServer | None, *, address_file: Path | None = None) -> str | None:
        """Publish one Agent's tools and optionally write its CLI discovery address."""
        if server is None:
            return None
        async with self.host_lock:
            if self.task_group is None:
                raise RuntimeError("The workflow's MCP host is not running.")
            if server in self.tool_endpoints:
                return self.tool_endpoints[server].url
            if self.server_origin is None:
                config = uvicorn.Config(
                    self.mcp_router, host="127.0.0.1", port=0, lifespan="off", ws="none",
                    access_log=False, log_config=None,
                )
                self.server_origin = await self.task_group.start(LocalMcpServer(config).listen)
            return await self.task_group.start(self.serve_tools, server, self.server_origin, address_file)

    async def unpublish(self, server: MCPServer | None) -> None:
        """Remove one Agent's route and close its MCP manager while keeping other Agents live."""
        if server is None:
            return
        with anyio.CancelScope(shield=True):
            async with self.host_lock:
                endpoint = self.tool_endpoints.get(server)
                if endpoint is not None:
                    endpoint.stop_event.set()
                    await endpoint.closed_event.wait()

    async def serve_tools(
        self, server: MCPServer, server_origin: str, address_file: Path | None, *, task_status: TaskStatus[str],
    ) -> None:
        """Own one Agent's route and MCP session manager on the workflow event loop."""
        path = f"/{token_urlsafe(24)}"
        route = Mount(path, app=server.streamable_http_app(stateless_http=True, json_response=True))
        endpoint = ToolServerEndpoint(f"{server_origin}{path}/mcp")
        try:
            async with server.session_manager.run():
                self.mcp_router.routes.append(route)
                self.tool_endpoints[server] = endpoint
                try:
                    if address_file is not None:
                        write_private_text(address_file, endpoint.url)
                    task_status.started(endpoint.url)
                    await endpoint.stop_event.wait()
                finally:
                    self.mcp_router.routes.remove(route)
                    del self.tool_endpoints[server]
                    if address_file is not None:
                        try:
                            if address_file.read_text(encoding="utf-8") == endpoint.url:
                                address_file.unlink()
                        except FileNotFoundError:
                            pass
        finally:
            endpoint.closed_event.set()


class LocalMcpServer(uvicorn.Server):
    """Embed Uvicorn without taking over the workflow application's signals."""

    def __init__(self, config: uvicorn.Config) -> None:
        """Bind the server configuration and initialize its task-group handshake state."""
        super().__init__(config)
        self.ready_status: TaskStatus[str] | None = None
        self.server_origin: str | None = None

    async def listen(self, *, task_status: TaskStatus[str]) -> None:
        """Serve the socket that received the ephemeral port until the host cancels it."""
        self.ready_status = task_status
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((self.config.host, self.config.port))
            host, port = listener.getsockname()
            self.server_origin = f"http://{host}:{port}"
            try:
                await self.serve(sockets=[listener])
            except asyncio.CancelledError:
                if self.started:
                    with anyio.CancelScope(shield=True):
                        await self.shutdown(sockets=[listener])
                raise

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Release the host only after Uvicorn accepts connections on the socket."""
        await super().startup(sockets=sockets)
        if self.ready_status is None or self.server_origin is None:
            raise RuntimeError("The MCP loopback server was not initialized before startup.")
        self.ready_status.started(self.server_origin)

    def capture_signals(self) -> AbstractContextManager[None]:
        """Leave process signals with the ForeRSI workflow supervisor."""
        return nullcontext()
