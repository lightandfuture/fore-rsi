# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""ForeRSI application startup shared by installed and module entry points."""

from collections.abc import Sequence

from fore_rsi.cli.parser import parse_args
from fore_rsi.logging import configure_logging
from fore_rsi.ui.launch_ui import launch_ui


def main(args: Sequence[str] | None = None) -> None:
    """Parse CLI input, configure diagnostics, and dispatch the selected command."""
    config = parse_args(args)
    configure_logging(config.logging)
    raise SystemExit(launch_ui(config))
