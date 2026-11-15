# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run the application event loop and translate command failures into process exit statuses."""

import asyncio
from subprocess import CalledProcessError
import sys

from fore_rsi.main import main


def cli() -> int:
    """Run the application, preserving native failures and interruption across task groups."""
    exit_status = 0
    try:
        asyncio.run(main())
    except* CalledProcessError as errors:
        exit_status = _command_exit_status(errors)
    except* KeyboardInterrupt:
        exit_status = 130
    return exit_status


def _command_exit_status(
    error: CalledProcessError | BaseExceptionGroup[CalledProcessError],
) -> int:
    """Print command diagnostics; preserve one native status or use 1 for multiple failures."""
    if isinstance(error, BaseExceptionGroup):
        statuses = [_command_exit_status(child) for child in error.exceptions]
        return statuses[0] if len(statuses) == 1 else 1

    if error.stderr:
        print(error.stderr, end="", file=sys.stderr)
    elif error.stdout:
        print(error.stdout, end="", file=sys.stderr)
    return error.returncode if error.returncode >= 0 else 128 - error.returncode


if __name__ == "__main__":
    raise SystemExit(cli())
