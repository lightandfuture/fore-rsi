# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Locate the bundled terminal and execute its asynchronous control commands."""

import asyncio
from importlib.metadata import distribution
import json
from pathlib import Path
import subprocess
from typing import Any

from fore_rsi.config import Config


async def run_terminal(
    arguments: list[str], session: str | None = None, *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    """Return a successful command result, preserving diagnostics on failure and reaping on cancellation."""
    command = terminal_command(arguments, session)
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if capture_output else None,
        stderr=asyncio.subprocess.PIPE if capture_output else None,
    )
    try:
        stdout, stderr = await process.communicate()
    except BaseException:
        # Control clients do not own a terminal. Cancel their process and drain
        # captured pipes before returning control to the caller.
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise

    result = subprocess.CompletedProcess(
        command,
        await process.wait(),
        stdout.decode("utf-8") if stdout is not None else None,
        stderr.decode("utf-8") if stderr is not None else None,
    )
    result.check_returncode()
    return result


async def query_terminal(arguments: list[str], session: str | None = None) -> dict[str, Any]:
    """Return a native JSON response without taking terminal input or blocking the event loop."""
    result = await run_terminal(arguments, session, capture_output=True)
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
