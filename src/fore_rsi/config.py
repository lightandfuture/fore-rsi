# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Application settings and command-line configuration for ForeRSI."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from tyro.conf import Positional, arg


@dataclass
class WorkflowConfig:
    """Task and agent execution."""

    # Select a built-in or project workflow by its declared name.
    name: Annotated[str | None, arg(name="workflow", prefix_name=False)] = None
    # Markdown task file.
    task: Annotated[Path | None, arg(prefix_name=False)] = None
    # Select the workflow's agent execution backend.
    harness: Annotated[str | None, arg(prefix_name=False)] = None


@dataclass
class UIConfig:
    """User interface configuration."""

    # Select a named ForeRSI session.
    session: Annotated[str | None, arg(prefix_name=False)] = None


@dataclass
class LoggingConfig:
    """Python diagnostic logging."""

    # Minimum diagnostic level.
    level: Annotated[
        Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        arg(name="log-level", prefix_name=False),
    ] = "INFO"
    # Append diagnostics to this file as well as stderr.
    file: Annotated[Path | None, arg(name="log-file", prefix_name=False)] = None
    # Diagnostic output format for stderr and the optional file.
    format: Annotated[Literal["text", "json"], arg(name="log-format", prefix_name=False)] = "text"


@dataclass
class Config:
    """User inputs and internal settings for ForeRSI session commands."""

    TERMINAL_EXECUTABLE_NAME: ClassVar[str] = "_terminal.exe" if os.name == "nt" else "_terminal"

    # Run or resume a session, list sessions, or delete a stopped session.
    session_action: Positional[Literal["run", "list", "delete"]] = "run"

    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
