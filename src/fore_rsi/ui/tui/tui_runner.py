# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Own asynchronous startup, waiting, and cleanup for the foreground terminal client."""

import asyncio
import os
from pathlib import Path
import signal
import subprocess

from fore_rsi.config import Config
from fore_rsi.ui.tui.work_progress.work_progress_runner import ensure_work_progress_pane
from fore_rsi.utils.terminal import terminal_command


class TuiRunner:
    """Manage the foreground client while the application supervises workflow execution."""

    def __init__(self, session_name: str | None) -> None:
        """Bind the application's session without starting a foreground client."""
        self._session_name = session_name if session_name is not None else Config.DEFAULT_SESSION_NAME
        self._working_directory = Path.cwd()
        self._command = terminal_command([], self._session_name)

    async def prepare(self) -> str:
        """Prepare the progress pane and return the terminal workspace shared with workflow agents."""
        return await ensure_work_progress_pane(self._session_name, self._working_directory)

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
