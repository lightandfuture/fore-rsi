# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Mount and run the work-progress interface without owning workflow execution."""

from pathlib import Path
import sys

from fore_rsi.config import Config
from fore_rsi.utils.terminal import ensure_terminal_pane


async def run_work_progress(session_directory: Path) -> None:
    """Run a page in an interactive terminal and release its terminal resources before returning."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("The work-progress page requires an interactive terminal.")

    from fore_rsi.ui.tui.work_progress.app import WorkProgressApp

    await WorkProgressApp(session_directory).run_async()


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
