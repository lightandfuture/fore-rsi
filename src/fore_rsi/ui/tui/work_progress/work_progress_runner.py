# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Mount and run the work-progress interface without owning workflow execution."""

import json
import os
import sys
from pathlib import Path

from fore_rsi.config import Config
from fore_rsi.utils.terminal import ensure_terminal_pane, run_terminal


async def run_work_progress(session_directory: Path) -> None:
    """Run a page in an interactive terminal and release its terminal resources before returning."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("The work-progress page requires an interactive terminal.")

    from fore_rsi.ui.tui.work_progress.app import WorkProgressApp

    embedded = False
    if pane_id := os.environ.get("HERDR_PANE_ID"):
        # The inherited socket and pane ID identify this terminal, not the session being viewed.
        result = await run_terminal(["pane", "get", pane_id], capture_output=True)
        pane = json.loads(result.stdout)["result"]["pane"]
        embedded = pane.get("managed_key") == Config.WORK_PROGRESS_PANE_KEY

    # Keep Ctrl+C as a key event even if Textual's signal opt-in was inherited.
    allow_signals = os.environ.pop("TEXTUAL_ALLOW_SIGNALS", None) if embedded else None
    try:
        await WorkProgressApp(session_directory, embedded=embedded).run_async()
    finally:
        if allow_signals is not None:
            os.environ["TEXTUAL_ALLOW_SIGNALS"] = allow_signals


async def ensure_work_progress_pane(session_name: str, working_directory: Path) -> str:
    """Return the workspace containing the session's native-managed work-progress page."""
    # Preserve user-site installations without importing modules from the pane's working directory.
    pane = await ensure_terminal_pane(
        session_name,
        key=Config.WORK_PROGRESS_PANE_KEY,
        working_directory=working_directory,
        label=Config.WORK_PROGRESS_LABEL,
        tokens={"fore_rsi_view": "progress"},
        command=[sys.executable, "-P", "-m", "fore_rsi", "workprogress", f"--session={session_name}"],
    )
    return pane["workspace_id"]
