# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Serve agent-specific MCP endpoints on one loopback listener per workflow session."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from secrets import token_urlsafe
import socket

import anyio
from anyio.abc import TaskGroup, TaskStatus
from mcp.server import MCPServer
from starlette.routing import Mount, Router
import uvicorn

from fore_rsi.utils.paths import write_private_text


@dataclass
class _ToolEndpoint:
    url: str
    stop: anyio.Event = field(default_factory=anyio.Event)
    closed: anyio.Event = field(default_factory=anyio.Event)


class ToolMcpHost:
    """Keep each agent's tool set reachable for its native session, independently of model turns."""

    def __init__(self) -> None:
        """Prepare an empty host; the first published tool set opens the listener."""
        self._router = Router()
        self._tasks: TaskGroup | None = None
        self._origin: str | None = None
        self._endpoints: dict[MCPServer, _ToolEndpoint] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def serve(self) -> AsyncIterator[None]:
        """Own the listener and all published endpoints until the application session exits."""
        async with anyio.create_task_group() as tasks:
            self._tasks = tasks
            try:
                yield
            finally:
                self._tasks = None
                self._origin = None
                tasks.cancel_scope.cancel()

    async def publish(self, server: MCPServer | None, *, address_file: Path | None = None) -> str | None:
        """Publish the agent's tools and, when requested, their address for the native client's lifetime."""
        if server is None:
            return None
        async with self._lock:
            if self._tasks is None:
                raise RuntimeError("The workflow's MCP host is not running.")
            if server in self._endpoints:
                return self._endpoints[server].url
            if self._origin is None:
                config = uvicorn.Config(
                    self._router, host="127.0.0.1", port=0, lifespan="off", ws="none",
                    access_log=False, log_config=None,
                )
                self._origin = await self._tasks.start(_LoopbackServer(config).listen)
            return await self._tasks.start(self._serve_tools, server, self._origin, address_file)

    async def unpublish(self, server: MCPServer | None) -> None:
        """Remove this runtime's route and wait for its MCP manager to close, leaving other agents live."""
        if server is None:
            return
        with anyio.CancelScope(shield=True):
            async with self._lock:
                endpoint = self._endpoints.get(server)
                if endpoint is not None:
                    endpoint.stop.set()
                    await endpoint.closed.wait()

    async def _serve_tools(
        self, server: MCPServer, origin: str, address_file: Path | None, *, task_status: TaskStatus[str],
    ) -> None:
        """Own an agent's private route and SDK session manager together on the workflow event loop."""
        path = f"/{token_urlsafe(24)}"
        route = Mount(path, app=server.streamable_http_app(stateless_http=True, json_response=True))
        endpoint = _ToolEndpoint(f"{origin}{path}/mcp")
        try:
            async with server.session_manager.run():
                self._router.routes.append(route)
                self._endpoints[server] = endpoint
                try:
                    if address_file is not None:
                        write_private_text(address_file, endpoint.url)
                    task_status.started(endpoint.url)
                    await endpoint.stop.wait()
                finally:
                    self._router.routes.remove(route)
                    del self._endpoints[server]
                    if address_file is not None:
                        try:
                            if address_file.read_text(encoding="utf-8") == endpoint.url:
                                address_file.unlink()
                        except FileNotFoundError:
                            pass
        finally:
            endpoint.closed.set()


class _LoopbackServer(uvicorn.Server):
    """Embed Uvicorn without taking over the application's shutdown signals."""

    async def listen(self, *, task_status: TaskStatus[str]) -> None:
        """Serve the socket that received the ephemeral port; cancellation drains the HTTP server."""
        self._ready = task_status
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((self.config.host, self.config.port))
            host, port = listener.getsockname()
            self._origin = f"http://{host}:{port}"
            try:
                await self.serve(sockets=[listener])
            except asyncio.CancelledError:
                if self.started:
                    with anyio.CancelScope(shield=True):
                        await self.shutdown(sockets=[listener])
                raise

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Release waiting runtimes only after Uvicorn accepts connections on the bound socket."""
        await super().startup(sockets=sockets)
        self._ready.started(self._origin)

    def capture_signals(self) -> AbstractContextManager[None]:
        """Leave process signals with the ForeRSI session supervisor."""
        return nullcontext()
