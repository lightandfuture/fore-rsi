# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""ForeRSI application startup shared by installed and module entry points."""

import asyncio
from collections.abc import Sequence
from typing import cast

from fore_rsi.cli.parser import parse_args
from fore_rsi.logging import setup_logging
from fore_rsi.rsi_workflows.launch_workflow import create_workflow_runner
from fore_rsi.session_manager import delete_session, list_sessions
from fore_rsi.ui.launch_ui import InterfaceClosed, create_ui_runner
from fore_rsi.utils.paths import resolve_project_path
from fore_rsi.utils.terminal import run_terminal


async def main(args: Sequence[str] | None = None) -> None:
    """Dispatch session commands and supervise workflow execution alongside the foreground UI."""
    config = parse_args(args)
    config.cache_dir = resolve_project_path(config.cache_dir)
    if config.workflow.task is not None:
        config.workflow.task = config.workflow.task.resolve()
    setup_logging(config.logging)

    match config.session_action:
        case "list":
            await list_sessions(config.cache_dir)
            return
        case "delete":
            await delete_session(cast(str, config.session))
            return

    ui_runner = create_ui_runner(config.session)
    workflow_runner = create_workflow_runner(config)

    # Prepare the shared server before the UI and workflow access it.
    await run_terminal(["server", "start"], config.session, capture_output=True)
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(workflow_runner.run(), name="workflow")
            await ui_runner.run()
            # TaskGroup owns cancellation so later shutdown signals cannot
            # interrupt a workflow's cleanup with another cancellation.
            raise InterfaceClosed()
    except* InterfaceClosed:
        pass
