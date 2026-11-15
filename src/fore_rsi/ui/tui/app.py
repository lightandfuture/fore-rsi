# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Own asynchronous startup, waiting, and cleanup for the foreground terminal client."""

import asyncio
import os
import signal
import subprocess

from fore_rsi.config import UIConfig
from fore_rsi.utils.terminal import run_terminal, terminal_command


class TuiApp:
    """Manage the foreground client while the application supervises workflow execution."""

    def __init__(self, config: UIConfig) -> None:
        """Resolve the client command without starting any process."""
        self._session = config.session
        self._command = terminal_command([], self._session)
        self._client: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """Prepare the native session and launch one client without waiting for it to exit."""
        if self._client is not None:
            raise RuntimeError("The terminal interface has already been started.")

        # Headless preparation leaves workspace creation to the workflow and
        # completes before the client and workflow access the same server.
        await run_terminal(["server", "start"], self._session, capture_output=True)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self._client = await asyncio.create_subprocess_exec(
            *self._command, creationflags=creationflags
        )

    async def wait(self) -> None:
        """Observe client exit without blocking workflow tasks, propagating a nonzero status."""
        if self._client is None:
            raise RuntimeError("The terminal interface has not been started.")

        returncode = await self._client.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, self._command)

    async def close(self) -> None:
        """Close and reap the foreground client; safe before startup and after an earlier close."""
        client = self._client
        if client is None:
            return

        if client.returncode is None:
            # Native termination handling restores terminal modes. On Windows,
            # the separate process group directs Ctrl+Break only to this client.
            if os.name == "nt":
                client.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                client.terminate()
        await client.wait()
        self._client = None


async def list_sessions() -> None:
    """Print native session names and status for the command dispatcher without attaching."""
    await run_terminal(["session", "list"])


async def delete_session(name: str) -> None:
    """Delete a stopped named session's native-owned data without removing project files."""
    await run_terminal(["session", "delete", name])
