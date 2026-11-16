# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Handle ForeRSI session listing and deletion for application callers."""

import json
from pathlib import Path

from loguru import logger

from fore_rsi.rsi_workflows.runtimes.workflow_runner import WorkflowRunner
from fore_rsi.utils.terminal import run_terminal


async def list_sessions(cache_dir: Path) -> None:
    """Print workflow and terminal server observations for the application's list command."""
    workflows = {
        session["session_name"]: session
        for session in WorkflowRunner.list_workflow_sessions(cache_dir)
    }
    result = await run_terminal(["session", "list", "--json"], capture_output=True)
    terminals = {session["name"]: session for session in json.loads(result.stdout)["sessions"]}

    rows = [("SESSION", "WORKFLOW", "WORKFLOW_STATE", "TERMINAL_SERVER")]
    for name in sorted(workflows.keys() | terminals.keys()):
        terminal = terminals.get(name)
        if terminal is None:
            terminal_status = "—"
        elif terminal.get("connection_error") is not None:
            terminal_status = "unavailable"
            logger.warning("{}: terminal server unavailable: {}", name, terminal["connection_error"])
        else:
            terminal_status = "running" if terminal["running"] else "stopped"
        workflow = workflows.get(name)
        if workflow is None:
            workflow_name = workflow_state = "—"
        else:
            workflow_name = workflow["workflow_name"]
            workflow_state = workflow.get("state", "—")
        rows.append((name, workflow_name, workflow_state, terminal_status))

    widths = [max(len(value) for value in column) for column in zip(*rows)]
    for row in rows:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip())


async def delete_session(name: str) -> None:
    """Stop a named terminal server and remove its session data for the application's delete command."""
    result = await run_terminal(["session", "list", "--json"], capture_output=True)
    session = next(
        (item for item in json.loads(result.stdout)["sessions"] if item["name"] == name),
        None,
    )
    # Native deletion owns name validation and default-session protection.
    if session is not None and not session["default"] and (
        session["running"] or session.get("connection_error") is not None
    ):
        await run_terminal(["session", "stop", "--", name], capture_output=True)
    await run_terminal(["session", "delete", "--", name])
