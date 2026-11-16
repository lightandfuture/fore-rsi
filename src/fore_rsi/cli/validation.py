# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Validate CLI option combinations before ForeRSI session execution."""

from collections.abc import Sequence
import sys

from fore_rsi.config import Config


def validate_config(config: Config, arguments: Sequence[str]) -> None:
    """Validate explicitly supplied CLI options, reporting usage errors with exit code 2."""
    supplied_options = {argument.partition("=")[0] for argument in arguments}
    if config.session_action != "run" and supplied_options & {"--workflow", "--task", "--harness"}:
        print(
            f"fore-rsi: {config.session_action} does not accept --workflow, --task, or --harness.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if config.session_action == "delete" and "--cache-dir" in supplied_options:
        print("fore-rsi: delete does not accept --cache-dir.", file=sys.stderr)
        raise SystemExit(2)

    if config.session_action == "list" and config.session is not None:
        print("fore-rsi: list does not accept --session.", file=sys.stderr)
        raise SystemExit(2)

    if config.session_action == "delete" and config.session is None:
        print("fore-rsi: delete requires --session NAME.", file=sys.stderr)
        raise SystemExit(2)
