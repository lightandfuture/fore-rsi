# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common role interface for workflow agents backed by harness sessions."""

from enum import StrEnum
from typing import ClassVar

from fore_rsi.harnesses_backend.base import AgentSession
from fore_rsi.rsi_workflows.workgroup import Workgroup


class AgentState(StrEnum):
    """Lifecycle states shared by agents and workflow scheduling."""

    READY = "ready"  # Runnable and eligible for scheduling.
    QUEUED = "queued"  # Enqueued for an execution slot.
    RUNNING = "running"
    SLEEPING = "sleeping"  # No runnable work until a message or dependency result arrives.
    PAUSING = "pausing"  # Settling native execution before releasing its slot.
    PAUSED = "paused"  # Scheduling disabled until the user or workflow explicitly resumes it.
    RETIRED = "retired"
    FAILED = "failed"


class BaseAgent:
    """Base class for role-specific agents using a harness session."""

    role_name: ClassVar[str]

    def __init__(
        self,
        agent_name: str,
        workgroup: Workgroup,
        session: AgentSession,
    ) -> None:
        """Bind the instance identity, workgroup, and harness session without starting execution."""
        self.agent_name = agent_name
        self.workgroup = workgroup
        self.session = session
        self.state = AgentState.READY

    def get_full_name(self) -> str:
        """Return the agent's workgroup-qualified name within its workflow."""
        return f"{self.workgroup.workgroup_name}/{self.agent_name}"
