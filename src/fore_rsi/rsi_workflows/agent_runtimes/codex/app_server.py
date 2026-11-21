# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Control one Codex thread through its local app-server proxy."""

import asyncio
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


class CodexAppServerError(RuntimeError):
    """Report an app-server transport or protocol failure."""


@dataclass(frozen=True)
class PendingCodexTurn:
    """Identify the turn that one queued or steered message must wait for."""

    thread_id: str
    mode: Literal["queue", "steer"]
    event_sequence: int
    active_turn_id: str | None = None
    turn_id: str | None = None


class CodexAppServer:
    """Own one JSON-RPC proxy connection to the Codex daemon for a workflow profile."""

    def __init__(self, profile: Path, executable: Path) -> None:
        """Bind the profile and launcher without starting a proxy process."""
        self.profile = profile
        self.executable = executable
        self.process: asyncio.subprocess.Process | None = None
        self.reader_task: asyncio.Task[None] | None = None
        self.proxy_exited = False
        self.initialized = False
        self.write_lock = asyncio.Lock()
        self.request_sequence = 0
        self.pending_requests: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.event_condition = asyncio.Condition()
        self.event_sequence = 0
        self.events: deque[tuple[int, str, dict[str, Any]]] = deque()
        self.thread_id: str | None = None
        self.active_turn_id: str | None = None

    async def connect(self) -> None:
        """Start the proxy and complete the app-server handshake once."""
        if self.process is not None:
            if self.initialized and not self.proxy_exited and self.process.returncode is None:
                return
            await self.close()
        self.process = await asyncio.create_subprocess_exec(
            str(self.executable),
            "app-server",
            "proxy",
            env={**os.environ, "CODEX_HOME": str(self.profile)},
            cwd=Path.cwd(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.proxy_exited = False
        self.initialized = False
        self.reader_task = asyncio.create_task(self.read_messages())
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "fore-rsi",
                    "title": "ForeRSI",
                    "version": "0.0.1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self.notify("initialized", {})
        self.initialized = True

    async def resume_thread(self, thread_id: str) -> None:
        """Join one existing thread and make it available to this control client."""
        await self.connect()
        if self.thread_id == thread_id:
            return
        await self.request(
            "thread/resume",
            {"threadId": thread_id, "excludeTurns": True},
        )
        self.thread_id = thread_id
        self.active_turn_id = None

    async def submit_message(
        self,
        thread_id: str,
        message: str,
        mode: Literal["queue", "steer"],
    ) -> PendingCodexTurn:
        """Submit a queue or steer message through the official app-server protocol."""
        if mode not in {"queue", "steer"}:
            raise ValueError(f"Unsupported Codex delivery mode: {mode!r}")
        await self.resume_thread(thread_id)
        active_turn_id = await self.current_active_turn(thread_id)
        event_sequence = self.event_sequence
        client_message_id = str(uuid4())
        input_items = [{"type": "text", "text": message}]
        if mode == "queue":
            await self.request(
                "thread/queue/add",
                {
                    "threadId": thread_id,
                    "clientUserMessageId": client_message_id,
                    "input": input_items,
                },
            )
            return PendingCodexTurn(
                thread_id=thread_id,
                mode=mode,
                event_sequence=event_sequence,
                active_turn_id=active_turn_id,
            )
        if active_turn_id is None:
            raise CodexAppServerError("Codex has no active turn to steer.")
        response = await self.request(
            "turn/steer",
            {
                "threadId": thread_id,
                "expectedTurnId": active_turn_id,
                "clientUserMessageId": client_message_id,
                "input": input_items,
            },
        )
        return PendingCodexTurn(
            thread_id=thread_id,
            mode=mode,
            event_sequence=event_sequence,
            turn_id=response.get("turnId") or active_turn_id,
            active_turn_id=active_turn_id,
        )

    async def wait_for_turn(self, pending: PendingCodexTurn) -> None:
        """Wait for the exact turn produced by one queued or steered message."""
        if pending.mode == "steer":
            if pending.turn_id is None:
                raise CodexAppServerError("Codex steer returned no turn id.")
            await self.wait_for_completion(
                pending.thread_id,
                pending.turn_id,
                pending.event_sequence,
            )
            return

        _, started = await self.wait_for_event(
            pending.event_sequence,
            lambda method, params: (
                method == "turn/started"
                and params.get("threadId") == pending.thread_id
                and params.get("turn", {}).get("id") != pending.active_turn_id
            ),
        )
        turn_id = started.get("turn", {}).get("id")
        if not isinstance(turn_id, str):
            raise CodexAppServerError("Codex turn/started notification had no turn id.")
        await self.wait_for_completion(pending.thread_id, turn_id, pending.event_sequence)

    async def current_active_turn(self, thread_id: str) -> str | None:
        """Read the active turn id from the resumed thread before steering or queueing."""
        if self.active_turn_id is not None:
            return self.active_turn_id
        response = await self.request(
            "thread/turns/list",
            {
                "threadId": thread_id,
                "limit": 1,
                "sortDirection": "desc",
                "itemsView": "summary",
            },
        )
        turns = response.get("data", [])
        for turn in reversed(turns):
            if turn.get("status") == "inProgress" and isinstance(turn.get("id"), str):
                self.active_turn_id = turn["id"]
                return self.active_turn_id
        return None

    async def wait_for_completion(
        self, thread_id: str, turn_id: str, after: int
    ) -> None:
        """Wait for a turn completion or a terminal app-server error."""
        while True:
            if self.process is None or self.proxy_exited or self.process.returncode is not None:
                raise CodexAppServerError("Codex app-server proxy is not running.")
            for sequence, method, params in self.events:
                if sequence <= after or params.get("threadId") != thread_id:
                    continue
                if method == "error" and params.get("turnId") == turn_id:
                    if not params.get("willRetry", False):
                        raise CodexAppServerError(
                            params.get("error", {}).get("message", "Codex turn failed.")
                        )
                if method != "turn/completed":
                    continue
                turn = params.get("turn", {})
                if turn.get("id") != turn_id:
                    continue
                status = turn.get("status")
                if status != "completed":
                    raise CodexAppServerError(
                        f"Codex turn {turn_id} ended with status {status!r}."
                    )
                self.active_turn_id = None
                self.discard_events_through(sequence)
                return
            async with self.event_condition:
                await self.event_condition.wait()

    async def wait_for_event(
        self,
        after: int,
        predicate: Callable[[str, dict[str, Any]], bool],
    ) -> tuple[int, dict[str, Any]]:
        """Wait for the first recorded app-server event matching a predicate."""
        while True:
            if self.process is None or self.proxy_exited or self.process.returncode is not None:
                raise CodexAppServerError("Codex app-server proxy is not running.")
            for sequence, method, params in self.events:
                if sequence > after and predicate(method, params):
                    return sequence, params
            async with self.event_condition:
                await self.event_condition.wait()

    def discard_events_through(self, sequence: int) -> None:
        """Discard notifications that no pending turn can still need."""
        while self.events and self.events[0][0] <= sequence:
            self.events.popleft()

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one JSON-RPC request and return its result or raise its server error."""
        if self.process is None or self.process.stdin is None:
            raise CodexAppServerError("Codex app-server proxy is not running.")
        self.request_sequence += 1
        request_id = self.request_sequence
        loop = asyncio.get_running_loop()
        response: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending_requests[request_id] = response
        try:
            await self.write_message(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            return await response
        except BaseException:
            self.pending_requests.pop(request_id, None)
            raise

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send one JSON-RPC notification without waiting for a response."""
        await self.write_message({"jsonrpc": "2.0", "method": method, "params": params})

    async def write_message(self, message: dict[str, Any]) -> None:
        """Write one newline-delimited JSON-RPC message to the proxy."""
        if self.process is None or self.process.stdin is None:
            raise CodexAppServerError("Codex app-server proxy is not running.")
        async with self.write_lock:
            self.process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            await self.process.stdin.drain()

    async def read_messages(self) -> None:
        """Route proxy responses and record turn notifications until the proxy exits."""
        if self.process is None or self.process.stdout is None:
            return
        failure = CodexAppServerError("Codex app-server proxy exited.")
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                method = message.get("method")
                if isinstance(method, str):
                    if "id" in message:
                        await self.handle_server_request(message)
                    else:
                        params = message.get("params")
                        if isinstance(params, dict):
                            await self.record_event(method, params)
                    continue
                if "id" in message:
                    request = self.pending_requests.pop(message["id"], None)
                    if request is None or request.done():
                        continue
                    if "error" in message:
                        error = message["error"]
                        request.set_exception(
                            CodexAppServerError(error.get("message", "Codex app-server request failed."))
                        )
                    else:
                        request.set_result(message.get("result", {}))
        except (asyncio.CancelledError, json.JSONDecodeError):
            raise
        except Exception as error:
            failure = CodexAppServerError(str(error))
        finally:
            for request in self.pending_requests.values():
                if not request.done():
                    request.set_exception(failure)
            self.pending_requests.clear()
            self.proxy_exited = True
            async with self.event_condition:
                self.event_condition.notify_all()

    async def handle_server_request(self, message: dict[str, Any]) -> None:
        """Reject unsupported server-initiated requests instead of leaving them pending."""
        await self.write_message(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {
                    "code": -32601,
                    "message": f"ForeRSI does not handle Codex server request {message.get('method')!r}.",
                },
            }
        )

    async def record_event(self, method: str, params: dict[str, Any]) -> None:
        """Record a notification and update the known active turn."""
        turn = params.get("turn", {})
        if params.get("threadId") == self.thread_id:
            if method == "turn/started" and isinstance(turn.get("id"), str):
                self.active_turn_id = turn["id"]
            elif method == "turn/completed":
                self.active_turn_id = None
        self.event_sequence += 1
        self.events.append((self.event_sequence, method, params))
        async with self.event_condition:
            self.event_condition.notify_all()

    async def close(self) -> None:
        """Stop the proxy process without stopping the shared Codex daemon."""
        reader_task = self.reader_task
        self.reader_task = None
        process = self.process
        self.process = None
        if reader_task is not None:
            reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await reader_task
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.terminate()
            await process.wait()
        self.proxy_exited = True
        self.initialized = False
        self.thread_id = None
        self.active_turn_id = None
        self.events.clear()
        self.event_sequence = 0
