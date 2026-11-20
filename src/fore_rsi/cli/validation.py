# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Validate CLI option combinations before ForeRSI session execution."""

import sys
from collections.abc import Sequence

from fore_rsi.config import Config


def validate_config(config: Config, arguments: Sequence[str]) -> None:
    """Validate explicitly supplied CLI options, reporting usage errors with exit code 2."""
    supplied_options = {argument.partition("=")[0] for argument in arguments}
    run_options = supplied_options & {"--workflow", "--task", "--harness", "--model", "--effort"}
    if config.session_action != "run" and run_options:
        print(f"fore-rsi: {config.session_action} does not accept {', '.join(sorted(run_options))}.", file=sys.stderr)
        raise SystemExit(2)

    if config.session_action == "list" and config.session is not None:
        print("fore-rsi: list does not accept --session.", file=sys.stderr)
        raise SystemExit(2)

    if config.session_action in {"stop", "delete", "workprogress"} and config.session is None:
        print(f"fore-rsi: {config.session_action} requires --session NAME.", file=sys.stderr)
        raise SystemExit(2)

    if config.session_action == "workprogress" and "--cache-dir" in supplied_options:
        print("fore-rsi: workprogress uses the session's saved storage; omit --cache-dir.", file=sys.stderr)
        raise SystemExit(2)

    if config.session_action != "run" or config.workflow.harness is None:
        return
    from fore_rsi.rsi_workflows.agent_runtimes import get_agent_runtime_class

    try:
        get_agent_runtime_class(config.workflow.harness)
    except ValueError as error:
        print(f"fore-rsi: {error}", file=sys.stderr)
        raise SystemExit(2) from None
