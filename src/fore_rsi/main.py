# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""ForeRSI application startup shared by installed and module entry points."""

import asyncio
from collections.abc import Sequence
from typing import cast

from fore_rsi.cli.parser import parse_args
from fore_rsi.logging import setup_logging
from fore_rsi.rsi_workflows.launch_workflow import create_workflow
from fore_rsi.ui.launch_ui import create_ui
from fore_rsi.ui.tui.app import delete_session, list_sessions


async def main(args: Sequence[str] | None = None) -> None:
    """Dispatch session commands and supervise workflow execution alongside the foreground UI."""
    config = parse_args(args)
    setup_logging(config.logging)

    match config.session_action:
        case "list":
            await list_sessions()
            return
        case "delete":
            await delete_session(cast(str, config.ui.session))
            return

    ui_runner = create_ui(config)
    workflow_runner = create_workflow(config)

    try:
        await ui_runner.start()
        async with asyncio.TaskGroup() as tasks:
            workflow_task = tasks.create_task(workflow_runner.run(), name="workflow")
            try:
                await ui_runner.wait()
            finally:
                # Request cancellation before leaving the group, which waits
                # for the workflow's own shutdown and persistence to finish.
                workflow_task.cancel()
    finally:
        await ui_runner.close()
