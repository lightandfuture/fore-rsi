# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Locate the bundled terminal and execute its asynchronous control commands."""

import asyncio
import json
import subprocess
from collections.abc import Mapping, Sequence
from importlib.metadata import distribution
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from fore_rsi.config import Config


class PaneLocation(TypedDict):
    """Placement and terminal identity returned by the native pane_info response."""

    pane_id: str
    workspace_id: str
    terminal_id: str
    created: NotRequired[bool]


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


async def ensure_terminal_pane(
    terminal_session_name: str,
    *,
    key: str,
    working_directory: Path,
    label: str,
    workspace_id: str | None = None,
    command: Sequence[str] = (),
    tokens: Mapping[str, str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> PaneLocation:
    """Create or reuse the keyed pane, preserving the native launch environment for new panes."""
    arguments = ["pane", "ensure", "--key", key, "--cwd", str(working_directory), "--label", label]
    if workspace_id is not None:
        arguments.extend(["--workspace", workspace_id])
    if environment:
        for name, value in sorted(environment.items()):
            arguments.extend(["--env", f"{name}={value}"])
    if command:
        arguments.extend(["--", *command])
    result = await run_terminal(arguments, terminal_session_name, capture_output=True)
    pane: PaneLocation = json.loads(result.stdout)["result"]["pane"]
    if tokens:
        await report_terminal_metadata(terminal_session_name, "pane", pane["pane_id"], tokens)
    return pane


async def report_terminal_metadata(
    session: str, resource: Literal["pane", "workspace"], resource_id: str, tokens: Mapping[str, str]
) -> None:
    """Publish workflow display metadata without changing the terminal's native agent state."""
    arguments = [resource, "report-metadata", resource_id, "--source", "fore-rsi"]
    for key, value in tokens.items():
        arguments.extend(["--token", f"{key}={value}"])
    await run_terminal(arguments, session, capture_output=True)


async def read_agent_session(
    pane_id: str, terminal_session_name: str | None = None
) -> dict[str, str] | None:
    """Return a pane's reported native session reference for harness backends, or None if absent."""
    result = await run_terminal(
        ["pane", "get", pane_id], terminal_session_name, capture_output=True
    )
    return json.loads(result.stdout)["result"]["pane"].get("agent_session")


def terminal_executable() -> Path:
    """Locate the bundled terminal; its native integration files are installed alongside it."""
    package = distribution("fore-rsi")
    for record in package.files or ():
        if record.parts[-3:] == ("libexec", "fore-rsi", Config.TERMINAL_EXECUTABLE_NAME):
            installed = Path(package.locate_file(record))
            return installed.parent.resolve() / installed.name
    raise FileNotFoundError(
        "The ForeRSI installation does not include its terminal executable. Reinstall ForeRSI."
    )


def terminal_command(arguments: list[str], session: str | None = None) -> list[str]:
    """Build a command addressing the selected native terminal session."""
    command = [str(terminal_executable())]
    if session is not None:
        command.extend(["--session", session])
    command.extend(arguments)
    return command
