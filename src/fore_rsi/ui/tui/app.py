# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Own asynchronous startup, waiting, and cleanup for the foreground terminal client."""

import asyncio
import os
import signal
import subprocess

from fore_rsi.utils.terminal import terminal_command


class TuiApp:
    """Manage the foreground client while the application supervises workflow execution."""

    def __init__(self, session_name: str | None) -> None:
        """Bind the application's session without starting a foreground client."""
        self._command = terminal_command([], session_name)

    async def run(self) -> None:
        """Run one foreground client and reap it on exit, failure, or cancellation."""
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        client = await asyncio.create_subprocess_exec(*self._command, creationflags=creationflags)
        try:
            returncode = await client.wait()
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, self._command)
        finally:
            if client.returncode is None:
                # Native termination handling restores terminal modes. On Windows,
                # the separate process group directs Ctrl+Break only to this client.
                if os.name == "nt":
                    client.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    client.terminate()
            await client.wait()
