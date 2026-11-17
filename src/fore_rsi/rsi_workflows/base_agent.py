# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common role interface for workflow agents backed by native harnesses."""

from enum import StrEnum
from typing import ClassVar

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
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
    """Base class for role-specific agents with a bound execution runtime."""

    role_name: ClassVar[str]

    def __init__(
        self,
        agent_name: str,
        workgroup: Workgroup,
        agent_runtime: AgentRuntime,
    ) -> None:
        """Bind the instance identity, workgroup, and agent runtime without starting execution."""
        self.agent_name = agent_name
        self.workgroup = workgroup
        self.agent_runtime = agent_runtime
        self.system_prompt: str | None = None
        self.state = AgentState.READY

    def get_full_name(self) -> str:
        """Return the agent's workgroup-qualified name within its workflow."""
        return f"{self.workgroup.workgroup_name}/{self.agent_name}"
