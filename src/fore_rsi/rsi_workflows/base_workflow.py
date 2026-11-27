# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Execution interface and discovery metadata shared by ForeRSI workflows."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from fore_rsi.config import WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import ToolMcpHost
from fore_rsi.rsi_workflows.base_agent import AgentState, BaseAgent
from fore_rsi.rsi_workflows.workflow_runtimes.agent_scheduler import AgentScheduler
from fore_rsi.rsi_workflows.workgroup import Workgroup


class BaseWorkflow(ABC):
    """Base class for named workflows invoked and supervised by WorkflowRunner."""

    # Name selected by --workflow, independent of the module and class names.
    workflow_name: ClassVar[str]
    agent_roles: ClassVar[dict[str, type[BaseAgent]]]

    def __init__(self, config: WorkflowConfig, session_directory: Path) -> None:
        """Bind workflow settings and storage, then initialize scheduling and workgroups."""
        self.config = config
        self.session_directory = session_directory
        self.tool_mcp_host = ToolMcpHost()
        self.agent_scheduler = AgentScheduler(
            role_classes=self.agent_roles,
        )
        # Workflow owns global Agent and Workgroup naming; Scheduler owns active reservations.
        self.agent_name_counters: dict[str, int] = {}
        self.workgroup_sequence = 0
        self.workgroups: dict[str, Workgroup] = {}
        self.global_workgroup = self.create_workgroup(WorkflowConfig.GLOBAL_WORKGROUP_NAME)

    @abstractmethod
    async def run_workflow(self, workspace_id: str) -> None:
        """Execute this workflow in the workspace prepared by WorkflowRunner."""
        ...

    async def close_workflow(self) -> None:
        """Close the workflow's agents and release their reservations before the runner records the outcome."""
        for workgroup_name, workgroup in tuple(self.workgroups.items()):
            for agent_name in tuple(workgroup.agents):
                await self.close_agent(workgroup_name, agent_name)

    def create_workgroup(self, workgroup_name: str | None = None) -> Workgroup:
        """Create an empty Workgroup with an explicit or workflow-assigned name."""
        if workgroup_name is None:
            self.workgroup_sequence += 1
            workgroup_name = f"workgroup-{self.workgroup_sequence}"
        if workgroup_name in self.workgroups:
            raise ValueError(
                f"Workgroup {workgroup_name!r} already exists in this workflow."
            )
        workgroup = Workgroup(workgroup_name)
        self.workgroups[workgroup_name] = workgroup
        return workgroup

    def next_agent_name(self, role_name: str) -> str:
        """Return a workflow-wide unique role-based instance name."""
        role_prefix = role_name.lower()
        agent_index = self.agent_name_counters.get(role_prefix, 0) + 1
        existing_agent_names = {
            agent.agent_name
            for workgroup in self.workgroups.values()
            for agent in workgroup.agents.values()
        }
        while f"{role_prefix}-{agent_index}" in existing_agent_names:
            agent_index += 1
        self.agent_name_counters[role_prefix] = agent_index
        return f"{role_prefix}-{agent_index}"

    async def close_agent(self, workgroup_name: str, agent_name: str) -> None:
        """Retire the member and release its slot without removing its workgroup entry."""
        workgroup = self.workgroups.get(workgroup_name)
        agent = workgroup.agents.get(agent_name) if workgroup is not None else None
        if agent is None:
            return
        agent.state = AgentState.RETIRED
        try:
            await agent.agent_runtime.close()
        finally:
            await self.agent_scheduler.release(agent)
