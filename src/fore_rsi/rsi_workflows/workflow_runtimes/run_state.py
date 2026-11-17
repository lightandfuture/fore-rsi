# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Recorded and observed execution states for workflow sessions."""

from enum import StrEnum


class WorkflowState(StrEnum):
    """Execution outcomes and host-liveness observations reported for workflow sessions."""

    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"
