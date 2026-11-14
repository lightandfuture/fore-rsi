# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Adapt ForeRSI session operations to the bundled native terminal."""

from importlib.metadata import distribution
import os
from pathlib import Path
import subprocess

from loguru import logger

from fore_rsi.config import UIConfig


def run_tui(config: UIConfig) -> int:
    """Run the terminal interface for the UI launcher and return its exit status.

    The native client owns terminal setup and restoration. Leaving the interface
    keeps the native background session and its pane processes running.
    """
    return _run_terminal([], config.session, lifecycle_level="INFO")


def list_sessions() -> int:
    """Print native session names and status for the UI dispatcher without attaching."""
    return _run_terminal(["session", "list"])


def stop_session(config: UIConfig) -> int:
    """Stop the selected native session and its panes while retaining saved session data."""
    return _run_terminal(["server", "stop"], config.session)


def _run_terminal(
    arguments: list[str], session: str | None = None, *, lifecycle_level: str = "DEBUG"
) -> int:
    """Run a native command, keeping routine command diagnostics below normal output."""
    command = [str(_terminal_executable())]
    if session is not None:
        command.extend(["--session", session])
    command.extend(arguments)

    logger.debug("Launching native terminal command", executable=command[0], arguments=arguments)
    # Inherit the terminal and foreground process group. On interruption, let
    # the native client restore terminal modes rather than killing it.
    with subprocess.Popen(command) as client:
        terminal_logger = logger.bind(child_pid=client.pid)
        terminal_logger.log(lifecycle_level, "Native terminal process started")
        try:
            returncode = client.wait()
        except KeyboardInterrupt:
            terminal_logger.info("Interrupted; waiting for the native terminal process to exit")
            client.wait()
            exit_code = 130
        else:
            exit_code = returncode if returncode >= 0 else 128 - returncode

    terminal_logger.log(
        lifecycle_level if exit_code in (0, 130) else "ERROR",
        "Native terminal process exited",
        exit_code=exit_code,
    )
    return exit_code


def _terminal_executable() -> Path:
    """Locate the private executable recorded by the Python package installer."""
    package = distribution("fore-rsi")
    filename = "_terminal.exe" if os.name == "nt" else "_terminal"
    for record in package.files or ():
        if record.parts[-3:] == ("libexec", "fore-rsi", filename):
            return Path(package.locate_file(record))

    raise FileNotFoundError(
        "The ForeRSI installation does not include its terminal executable. Reinstall ForeRSI."
    )
