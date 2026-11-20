# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""ForeRSI application startup shared by installed and module entry points."""

import asyncio
from collections.abc import Sequence
from typing import cast

from fore_rsi.cli.parser import parse_args
from fore_rsi.config import Config
from fore_rsi.logging import setup_logging
from fore_rsi.session_manager import (
    bind_session_storage,
    delete_session,
    get_workflow_session_directory,
    list_sessions,
    resolve_session_storage,
    stop_session,
)
from fore_rsi.ui.launch_ui import InterfaceClosed, create_ui_runner
from fore_rsi.ui.tui.work_progress.work_progress_runner import run_work_progress
from fore_rsi.utils.paths import resolve_project_path


async def main(args: Sequence[str] | None = None) -> None:
    """Dispatch session commands and supervise workflow execution alongside the foreground UI."""
    config = parse_args(args)
    setup_logging(config.logging)
    if config.session_action == "workprogress":
        await run_work_progress(get_workflow_session_directory(cast(str, config.session)))
        return

    config.cache_dir = resolve_project_path(config.cache_dir)
    if config.workflow.task is not None:
        config.workflow.task = config.workflow.task.resolve()
    match config.session_action:
        case "list":
            await list_sessions(config.cache_dir)
            return
        case "stop":
            await stop_session(cast(str, config.session), config.cache_dir)
            return
        case "delete":
            await delete_session(cast(str, config.session), config.cache_dir)
            return

    # Only a workflow host needs agent SDKs and custom workflow discovery.
    from fore_rsi.rsi_workflows.agent_runtimes import get_agent_runtime_class
    from fore_rsi.rsi_workflows.launch_workflow import create_workflow_runner

    if config.session is None:
        config.session = Config.DEFAULT_SESSION_NAME
    config.cache_dir = resolve_session_storage(config.session, config.cache_dir)
    ui_runner = create_ui_runner(config.session)
    workflow_runner = create_workflow_runner(config)
    await get_agent_runtime_class(workflow_runner.harness).ensure_installed()

    # Finish preparation before recording a new binding; keep subprocess waits outside its transaction.
    await ui_runner.start_server()
    bind_session_storage(config.session, config.cache_dir)
    workspace_id = await ui_runner.prepare()
    # The foreground conversation can still call tools after workflow startup returns.
    try:
        async with workflow_runner.workflow.tool_mcp_host.serve(), asyncio.TaskGroup() as tasks:
            tasks.create_task(workflow_runner.run(workspace_id), name="workflow")
            await ui_runner.run()
            # TaskGroup owns cancellation so later shutdown signals cannot
            # interrupt a workflow's cleanup with another cancellation.
            raise InterfaceClosed()
    except* InterfaceClosed:
        pass
