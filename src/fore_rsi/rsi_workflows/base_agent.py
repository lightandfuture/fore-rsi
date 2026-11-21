# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Common role interface for workflow agents backed by native harnesses."""

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.agent_runtimes import AgentTool, create_agent_runtime
from fore_rsi.rsi_workflows.agent_runtimes.base_runtime import MessageDeliveryMode
from fore_rsi.rsi_workflows.workgroup import Workgroup

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow


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
        agent_config: AgentConfig,
        *,
        workflow: "BaseWorkflow",
        tools: Sequence[AgentTool] = (),
    ) -> None:
        """Create the member's unstarted runtime with the tools selected by its role."""
        self.agent_name = agent_name
        self.workgroup = workgroup
        self.system_prompt: str | None = None
        self.state = AgentState.READY
        self.agent_runtime = create_agent_runtime(
            agent_config, workflow_directory=workflow.session_directory,
            workgroup_name=workgroup.workgroup_name, agent_name=agent_name,
            tool_mcp_host=workflow.tool_mcp_host, tools=tools,
        )

    async def send_message(
        self,
        message: str,
        mode: MessageDeliveryMode = "queue",
    ) -> None:
        """Send one workflow message through the selected delivery mode."""
        await self.agent_runtime.send_message(message, mode=mode)

    def get_full_name(self) -> str:
        """Return the agent's workgroup-qualified name within its workflow."""
        return f"{self.workgroup.workgroup_name}/{self.agent_name}"
