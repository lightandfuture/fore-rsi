# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Bind ForeRSI sessions to storage and coordinate listing, shutdown, and deletion."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3

from loguru import logger

from fore_rsi.config import Config, WorkflowConfig
from fore_rsi.rsi_workflows.workflow_runtimes.run_state import WorkflowState
from fore_rsi.rsi_workflows.workflow_runtimes.workflow_runner import WorkflowRunner
from fore_rsi.utils.terminal import run_terminal


def resolve_session_storage(session_name: str | None, cache_dir: Path) -> Path:
    """Return the saved location for application startup, or the selected directory for a new session."""
    name = session_name if session_name is not None else Config.DEFAULT_SESSION_NAME
    return _read_session_bindings().get(name, cache_dir)


def get_workflow_session_directory(session_name: str) -> Path:
    """Return an existing session's workflow directory for readers without creating a binding or data."""
    cache_dir = _read_session_bindings().get(session_name)
    if cache_dir is None:
        raise ValueError(f"Session {session_name!r} has no saved storage binding.")
    return cache_dir / WorkflowConfig.SESSIONS_DIR_NAME / session_name


def bind_session_storage(session_name: str | None, cache_dir: Path) -> None:
    """Register prepared session storage, rejecting a different location chosen by a concurrent startup."""
    name = session_name if session_name is not None else Config.DEFAULT_SESSION_NAME
    with _session_index() as index:
        index.execute(
            "INSERT INTO sessions (session_name, cache_dir) VALUES (?, ?) "
            "ON CONFLICT(session_name) DO NOTHING",
            (name, str(cache_dir)),
        )
        row = index.execute(
            "SELECT cache_dir FROM sessions WHERE session_name = ?", (name,)
        ).fetchone()
        if Path(row[0]) != cache_dir:
            raise RuntimeError(
                f"Session {name!r} was bound to {row[0]!r} by another startup. "
                "Run the command again to use that location."
            )


async def list_sessions(cache_dir: Path) -> None:
    """Print registered workflows and terminal servers, also including unbound records in the given cache."""
    bindings = _read_session_bindings()
    workflows = {}
    for directory in dict.fromkeys([cache_dir, *bindings.values()]):
        for session in WorkflowRunner.list_workflow_sessions(directory):
            name = session["session_name"]
            if bindings.get(name, cache_dir) == directory:
                workflows[name] = session
    result = await run_terminal(["session", "list", "--json"], capture_output=True)
    terminals = {session["name"]: session for session in json.loads(result.stdout)["sessions"]}

    rows = [("SESSION", "WORKFLOW", "WORKFLOW_STATE", "TERMINAL_SERVER")]
    for name in sorted(bindings.keys() | workflows.keys() | terminals.keys()):
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


async def stop_session(name: str, cache_dir: Path) -> None:
    """Stop the named workflow and terminal for CLI callers, preserving session data and its binding."""
    session = await _find_terminal_session(name)
    cache_dir = resolve_session_storage(name, cache_dir)
    workflow_state = await _stop_workflow_and_terminal(name, cache_dir, session)
    if session is None and workflow_state is None:
        raise ValueError(f"Session {name!r} was not found.")
    print(f"stopped session {name}")


async def delete_session(name: str, cache_dir: Path) -> None:
    """Stop and delete a named workflow and terminal session, preserving project and agent-owned data."""
    session = await _find_terminal_session(name)
    # Reject the protected default before stopping either side.
    if session is not None and session["default"]:
        await run_terminal(["session", "delete", "--", name], capture_output=True)
        return

    bound_cache_dir = _read_session_bindings().get(name)
    if bound_cache_dir is not None:
        cache_dir = bound_cache_dir
    workflow_state = await _stop_workflow_and_terminal(name, cache_dir, session)
    if session is not None or workflow_state is None:
        await run_terminal(["session", "delete", "--", name], capture_output=True)

    # Keep workflow records until terminal shutdown and deletion have succeeded.
    await WorkflowRunner.delete_workflow_session(name, cache_dir)
    if bound_cache_dir is not None:
        with _session_index() as index:
            index.execute(
                "DELETE FROM sessions WHERE session_name = ? AND cache_dir = ?",
                (name, str(bound_cache_dir)),
            )
    print(f"deleted session {name}")


async def _find_terminal_session(name: str) -> dict[str, object] | None:
    """Return the exact inventory entry used by stop and delete to select a terminal session."""
    result = await run_terminal(["session", "list", "--json"], capture_output=True)
    return next(
        (session for session in json.loads(result.stdout)["sessions"] if session["name"] == name),
        None,
    )


async def _stop_workflow_and_terminal(
    name: str, cache_dir: Path, session: dict[str, object] | None
) -> WorkflowState | None:
    """Wait for workflow cleanup before stopping its terminal, retaining both sides' data for callers."""
    workflow_state = await WorkflowRunner.stop_workflow_session(name, cache_dir)
    if session is not None and (session["running"] or session.get("connection_error") is not None):
        await run_terminal(["session", "stop", "--", name], capture_output=True)
    return workflow_state


def _read_session_bindings() -> dict[str, Path]:
    """Read storage locations for application commands without creating an unused index."""
    if not Config.SESSION_INDEX_PATH.exists():
        return {}
    with _session_index() as index:
        return {
            name: Path(directory)
            for name, directory in index.execute("SELECT session_name, cache_dir FROM sessions")
        }


@contextmanager
def _session_index() -> Iterator[sqlite3.Connection]:
    """Own one index transaction and connection; the primary key keeps names bound to one location."""
    Config.SESSION_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(Config.SESSION_INDEX_PATH)) as index, index:
        index.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "session_name TEXT PRIMARY KEY NOT NULL, cache_dir TEXT NOT NULL)"
        )
        yield index
