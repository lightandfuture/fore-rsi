# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""ForeRSI application startup shared by installed and module entry points."""

from collections.abc import Sequence
from typing import cast

from fore_rsi.cli.parser import parse_args
from fore_rsi.logging import setup_logging
from fore_rsi.rsi_workflows.launch_workflow import create_workflow
from fore_rsi.ui.launch_ui import create_ui
from fore_rsi.ui.tui.app import delete_session, list_sessions


def main(args: Sequence[str] | None = None) -> None:
    """Dispatch session commands and coordinate UI and workflow startup and shutdown."""
    config = parse_args(args)
    setup_logging(config.logging)

    match config.session_action:
        case "list":
            list_sessions()
            return
        case "delete":
            delete_session(cast(str, config.ui.session))
            return

    ui = create_ui(config)
    workflow = create_workflow(config)

    try:
        ui.start()
        workflow.start()
        ui.wait()
    finally:
        try:
            workflow.close()
        finally:
            ui.close()
