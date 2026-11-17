# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Execution interface and discovery metadata shared by ForeRSI workflows."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from fore_rsi.config import WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp_host import ToolMcpHost
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.workflow_runtimes.agent_scheduler import AgentScheduler
from fore_rsi.rsi_workflows.workgroup import Workgroup


class BaseWorkflow(ABC):
    """Base class for named workflows invoked and supervised by WorkflowRunner."""

    # Name selected by --workflow, independent of the module and class names.
    workflow_name: ClassVar[str]
    agent_roles: ClassVar[tuple[type[BaseAgent], ...]]

    def __init__(self, config: WorkflowConfig, session_directory: Path) -> None:
        """Bind workflow settings and storage, then initialize scheduling and workgroups."""
        self._config = config
        self.session_directory = session_directory
        self.tool_mcp_host = ToolMcpHost()
        self.agent_scheduler = AgentScheduler(agent_roles=self.agent_roles)
        self.workgroups: dict[str, Workgroup] = {}
        self.global_workgroup = self.create_workgroup(WorkflowConfig.GLOBAL_WORKGROUP_NAME)

    @abstractmethod
    async def run(self, workspace_id: str) -> None:
        """Execute within the prepared terminal workspace, propagating errors and cancellation."""
        ...

    def create_workgroup(
        self,
        workgroup_name: str,
        initial_agents: Sequence[tuple[type[BaseAgent], str, AgentRuntime]] = (),
    ) -> Workgroup:
        """Create a workgroup and its initial agents without starting execution.

        Initial agents use (agent_class, agent_name, agent_runtime) tuples.
        """
        if workgroup_name in self.workgroups:
            raise ValueError(
                f"Workgroup {workgroup_name!r} already exists in this workflow."
            )

        workgroup = Workgroup(workgroup_name)
        self.workgroups[workgroup_name] = workgroup
        try:
            for agent_class, agent_name, agent_runtime in initial_agents:
                self.create_agent(
                    agent_class=agent_class,
                    agent_name=agent_name,
                    workgroup_name=workgroup_name,
                    agent_runtime=agent_runtime,
                )
        except BaseException:
            # Keep failed initialization from leaving a partially populated group.
            del self.workgroups[workgroup_name]
            raise
        return workgroup

    def create_agent(
        self,
        agent_class: type[BaseAgent],
        agent_name: str,
        workgroup_name: str,
        agent_runtime: AgentRuntime,
    ) -> BaseAgent:
        """Create and register an agent, creating its workgroup when absent."""
        workgroup = self.workgroups.get(workgroup_name)
        if workgroup is None:
            workgroup = self.create_workgroup(workgroup_name)

        if agent_name in workgroup.agents:
            raise ValueError(
                f"Agent {agent_name!r} already exists in workgroup {workgroup_name!r}."
            )

        agent = agent_class(agent_name, workgroup, agent_runtime)
        workgroup.agents[agent_name] = agent
        return agent

    def get_agent(self, workgroup_name: str, agent_name: str) -> BaseAgent:
        """Return an existing agent from the named workgroup."""
        return self.workgroups[workgroup_name].agents[agent_name]
