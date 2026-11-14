# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Validate CLI option combinations before ForeRSI session execution."""

import sys

from fore_rsi.config import Config


def validate_config(config: Config) -> None:
    """Check CLI option combinations, reporting failures and exiting with code 2."""
    if config.session_action != "run" and any(
        value is not None
        for value in (config.workflow.name, config.workflow.task, config.workflow.harness)
    ):
        print(
            f"fore-rsi: {config.session_action} does not accept --workflow, --task, or --harness.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if config.session_action == "list" and config.ui.session is not None:
        print("fore-rsi: list does not accept --session.", file=sys.stderr)
        raise SystemExit(2)
