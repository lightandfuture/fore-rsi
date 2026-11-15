# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Own startup, waiting, and cleanup for the foreground terminal client."""

import os
import signal
import subprocess

from fore_rsi.config import UIConfig
from fore_rsi.utils.terminal import run_terminal, terminal_command


class TuiApp:
    """Manage the foreground client; the application coordinates workflow shutdown separately."""

    def __init__(self, config: UIConfig) -> None:
        """Keep the UI configuration without starting a server or client process."""
        self._config = config
        self._client: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        """Prepare the native session and launch one client without waiting for it to exit."""
        if self._client is not None:
            raise RuntimeError("The terminal interface has already been started.")

        # Headless preparation leaves workspace creation to the workflow and
        # completes before the client and workflow access the same server.
        run_terminal(["server", "start"], self._config.session, capture_output=True)
        command = terminal_command([], self._config.session)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self._client = subprocess.Popen(command, creationflags=creationflags)

    def wait(self) -> None:
        """Wait for the foreground client and propagate a nonzero exit to the application."""
        if self._client is None:
            raise RuntimeError("The terminal interface has not been started.")

        returncode = self._client.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, self._client.args)

    def close(self) -> None:
        """Close and reap the foreground client; safe before startup and after an earlier close."""
        client = self._client
        if client is None:
            return

        if client.poll() is None:
            # Native termination handling restores terminal modes. On Windows,
            # the separate process group directs Ctrl+Break only to this client.
            if os.name == "nt":
                client.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                client.terminate()
        client.wait()
        self._client = None


def list_sessions() -> None:
    """Print native session names and status for the command dispatcher without attaching."""
    run_terminal(["session", "list"])


def delete_session(name: str) -> None:
    """Delete a stopped named session's native-owned data without removing project files."""
    run_terminal(["session", "delete", name])
