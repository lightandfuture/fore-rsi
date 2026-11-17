# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Application settings and command-line configuration for ForeRSI."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from platformdirs import user_state_path
from tyro.conf import Positional, arg


@dataclass
class HarnessConfig:
    """Execution settings supplied by workflows when constructing an agent runtime."""

    # Select the native execution backend.
    harness: str = "pi"
    # None preserves the selected harness's model settings.
    model: str | None = None


@dataclass
class WorkflowConfig:
    """Task and agent execution."""

    GLOBAL_WORKGROUP_NAME: ClassVar[str] = "global"
    SESSIONS_DIR_NAME: ClassVar[str] = "workflows"
    SESSION_RECORD_NAME: ClassVar[str] = "workflow.json"
    # Interval between host-exit checks while stopping a workflow.
    STOP_POLL_INTERVAL_SECONDS: ClassVar[float] = 0.1

    # Select a built-in or project workflow by its declared name.
    workflow_name: Annotated[str, arg(name="workflow", prefix_name=False)] = "default"
    # Markdown task file.
    task: Annotated[Path | None, arg(prefix_name=False)] = None
    # Select the agent execution backend: pi, codex, or claude (Claude Code).
    harness: Annotated[str, arg(prefix_name=False)] = HarnessConfig.harness


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
    DEFAULT_SESSION_NAME: ClassVar[str] = "default"
    WORK_PROGRESS_PANE_KEY: ClassVar[str] = "fore-rsi.work-progress"
    WORK_PROGRESS_LABEL: ClassVar[str] = "Work progress"
    SESSION_INDEX_PATH: ClassVar[Path] = (
        user_state_path("fore-rsi", appauthor=False) / "sessions.sqlite3"
    )

    # Run or resume, list, stop, delete a session, or open its work-progress page.
    session_action: Positional[Literal["run", "list", "stop", "delete", "workprogress"]] = "run"
    # Select the ForeRSI session shared by its workflow and interface.
    session: Annotated[str | None, arg(prefix_name=False)] = None
    # Initial workflow storage, relative to the project Git root or startup directory outside Git.
    # Existing sessions reuse their saved location.
    cache_dir: Annotated[Path, arg(name="cache-dir", prefix_name=False)] = Path("./cache")

    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
