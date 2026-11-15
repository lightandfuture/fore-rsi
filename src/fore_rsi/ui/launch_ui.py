# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Construct the user interface for the ForeRSI application entry point."""

from fore_rsi.config import Config
from fore_rsi.ui.tui.app import TuiApp


def create_ui(config: Config) -> TuiApp:
    """Return an unstarted terminal interface whose lifetime is managed by the application."""
    return TuiApp(config.ui)
