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

    SESSIONS_DIR_NAME: ClassVar[str] = "workflows"
    SESSION_RECORD_NAME: ClassVar[str] = "workflow.json"
    # Interval between host-exit checks while stopping a workflow.
    STOP_POLL_INTERVAL_SECONDS: ClassVar[float] = 0.1

    # Select a built-in or project workflow by its declared name.
    workflow_name: Annotated[str, arg(name="workflow", prefix_name=False)] = "default"
    # Markdown task file.
    task: Annotated[Path | None, arg(prefix_name=False)] = None
    # Select the workflow's agent execution backend.
    harness: Annotated[str | None, arg(prefix_name=False)] = None


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
    # Select the ForeRSI session shared by its workflow and interface.
    session: Annotated[str | None, arg(prefix_name=False)] = None
    # Local runtime data, relative to the project Git root or startup directory outside Git.
    cache_dir: Annotated[Path, arg(name="cache-dir", prefix_name=False)] = Path("./cache")

    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
