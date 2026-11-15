# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Locate the bundled terminal and run its non-interactive control commands."""

from importlib.metadata import distribution
import json
from pathlib import Path
import subprocess
from typing import Any

from fore_rsi.config import Config


def run_terminal(
    arguments: list[str], session: str | None = None, *, capture_output: bool = False
) -> None:
    """Run a control command, optionally retaining its diagnostics for the caller's error handler."""
    subprocess.run(
        terminal_command(arguments, session),
        stdin=subprocess.DEVNULL,
        capture_output=capture_output,
        text=True,
        check=True,
    )


def query_terminal(arguments: list[str], session: str | None = None) -> dict[str, Any]:
    """Return a native JSON response for workflow orchestration without taking terminal input."""
    result = subprocess.run(
        terminal_command(arguments, session),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def terminal_command(arguments: list[str], session: str | None = None) -> list[str]:
    """Build a command for UI and backend callers using the executable recorded by the installer."""
    package = distribution("fore-rsi")
    for record in package.files or ():
        if record.parts[-3:] == ("libexec", "fore-rsi", Config.TERMINAL_EXECUTABLE_NAME):
            executable = Path(package.locate_file(record))
            break
    else:
        raise FileNotFoundError(
            "The ForeRSI installation does not include its terminal executable. Reinstall ForeRSI."
        )

    command = [str(executable)]
    if session is not None:
        command.extend(["--session", session])
    command.extend(arguments)
    return command
