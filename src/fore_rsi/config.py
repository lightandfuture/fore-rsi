# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Session, workflow, display, and diagnostic configuration for ForeRSI."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from tyro.conf import Positional, arg


@dataclass
class WorkflowConfig:
    """Task and agent execution."""

    # Select a workflow.
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
    """Inputs for running, listing, reconnecting to, or stopping ForeRSI sessions."""

    # Run, list, reconnect to, or stop ForeRSI sessions.
    session_action: Positional[Literal["run", "list", "stop"]] = "run"

    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
