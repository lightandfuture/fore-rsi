# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Construct the user interface for the ForeRSI application entry point."""

from fore_rsi.ui.tui.app import TuiApp


class InterfaceClosed(Exception):
    """End the session task group when its foreground interface exits."""


def create_ui_runner(session_name: str | None) -> TuiApp:
    """Return an unstarted interface for the session selected by the application."""
    return TuiApp(session_name)
