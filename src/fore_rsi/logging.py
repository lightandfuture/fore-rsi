# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Configure process diagnostics without owning conversations or experiment records."""

from __future__ import annotations

import inspect
import logging as stdlib_logging
import sys

from loguru import logger

from fore_rsi.config import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """Configure application diagnostics from the parsed logging options.

    The application entry point owns sink configuration; Loguru closes synchronous
    sinks at process exit. Independent processes own separate files.
    """
    settings = {
        "level": config.level,
        "format": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS Z} | {level: <8} | "
            "{process.id} | {name}:{line} | {message}"
        ),
        "serialize": config.format == "json",
        "colorize": False,
        "backtrace": False,
        "diagnose": False,
        "enqueue": False,
    }
    handlers = [{**settings, "sink": sys.stderr}]
    if config.file is not None:
        # Loguru accepts filename templates, but this option is a literal filesystem path.
        filename = str(config.file.expanduser()).replace("{", "{{").replace("}", "}}")
        handlers.append({**settings, "sink": filename, "encoding": "utf-8"})
    logger.configure(handlers=handlers)
    stdlib_logging.basicConfig(
        handlers=[_InterceptHandler()],
        level=logger.level(config.level).no,
        force=True,
    )


class _InterceptHandler(stdlib_logging.Handler):
    """Forward standard-library diagnostics to the application's Loguru sinks."""

    def emit(self, record: stdlib_logging.LogRecord) -> None:
        """Preserve the source logger, level, call site, and original exception."""
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Skip this adapter and standard logging frames to retain the caller's location.
        frame, depth = inspect.currentframe(), 0
        while frame is not None:
            filename = frame.f_code.co_filename
            is_logging = filename == stdlib_logging.__file__
            is_import = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging or is_import):
                break
            frame = frame.f_back
            depth += 1

        logger.patch(lambda event: event.update(name=record.name)).opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())
