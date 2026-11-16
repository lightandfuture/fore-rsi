# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Run the application event loop and translate command failures into process exit statuses."""

import asyncio
import signal
from subprocess import CalledProcessError
import sys
from types import FrameType
from typing import cast

from fore_rsi.main import main


def cli() -> int:
    """Run the application, preserving native failures and interruption across task groups."""
    exit_status = 0
    try:
        exit_status = asyncio.run(_run_with_shutdown_signals())
    except* CalledProcessError as errors:
        exit_status = _command_exit_status(errors)
    except* KeyboardInterrupt:
        exit_status = 130
    return exit_status


async def _run_with_shutdown_signals() -> int:
    """Run the CLI application with graceful hangup/termination and restore its signal handlers."""
    loop = asyncio.get_running_loop()
    task = cast(asyncio.Task[int], asyncio.current_task())
    shutdown_signal: int | None = None

    def cancel_application(signum: int) -> None:
        nonlocal shutdown_signal
        if shutdown_signal is None:
            shutdown_signal = signum
            # Repeated window-close signals must leave asynchronous cleanup running.
            if not task.cancelling():
                task.cancel()

    def request_shutdown(signum: int, _frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(cancel_application, signum)

    termination_signals = [signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        termination_signals.append(signal.SIGHUP)
    previous_handlers = {}
    try:
        for signum in termination_signals:
            previous_handlers[signum] = signal.signal(signum, request_shutdown)
        try:
            await main()
        except asyncio.CancelledError:
            if shutdown_signal is None:
                raise
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)

    if shutdown_signal is not None:
        task.uncancel()
        return 128 + shutdown_signal
    return 0


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
