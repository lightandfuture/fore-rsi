# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Dispatch ForeRSI session actions through the UI backend."""

from loguru import logger

from fore_rsi.config import Config, WorkflowConfig
from fore_rsi.logging import configure_logging
from fore_rsi.ui.tui.app import list_sessions, run_tui, stop_session


def launch_ui(config: Config) -> int:
    """Execute the selected session action for the application and return its exit status."""
    context: dict[str, str] = {"session_action": config.session_action}
    if config.ui.session is not None:
        context["session_name"] = config.ui.session

    with logger.contextualize(**context):
        logger.debug("Executing session action")
        try:
            match config.session_action:
                case "list":
                    return list_sessions()
                case "stop":
                    return stop_session(config.ui)
                case "run":
                    if config.workflow != WorkflowConfig():
                        logger.error("Workflow execution is not implemented.")
                        return 1
                    configure_logging(config.logging, console_enabled=False)
                    return run_tui(config.ui)
        except OSError as error:
            configure_logging(config.logging)
            logger.opt(exception=error).error("Session action failed: {}", error)
            return 1
