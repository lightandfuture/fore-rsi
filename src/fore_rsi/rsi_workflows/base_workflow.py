# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Execution interface and discovery metadata shared by ForeRSI workflows."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from fore_rsi.config import WorkflowConfig
from fore_rsi.harnesses_backend.base import AgentSession
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.runtimes.agent_scheduler import AgentScheduler
from fore_rsi.rsi_workflows.workgroup import Workgroup


class BaseWorkflow(ABC):
    """Base class for named workflows invoked and supervised by WorkflowRunner."""

    # Name selected by --workflow, independent of the module and class names.
    workflow_name: ClassVar[str]
    agent_roles: ClassVar[tuple[type[BaseAgent], ...]]
    entry_agent_class: ClassVar[type[BaseAgent]]

    def __init__(self, config: WorkflowConfig) -> None:
        """Initialize workflow settings, shared agent scheduling, and the global workgroup."""
        self._config = config
        self.agent_scheduler = AgentScheduler(quotas=())
        self.workgroups: dict[str, Workgroup] = {}
        self.global_workgroup = self.create_workgroup("global")


    @abstractmethod
    async def run(self) -> None:
        """Execute the workflow; return on completion and propagate errors or cancellation."""
        ...

    def create_workgroup(
        self,
        workgroup_name: str,
        initial_agents: Sequence[tuple[type[BaseAgent], str, AgentSession]] = (),
    ) -> Workgroup:
        """Create a workgroup and its initial agents without starting execution.

        Initial agents use (agent_class, agent_name, session) tuples.
        """
        if workgroup_name in self.workgroups:
            raise ValueError(
                f"Workgroup {workgroup_name!r} already exists in this workflow."
            )

        workgroup = Workgroup(workgroup_name)
        self.workgroups[workgroup_name] = workgroup
        try:
            for agent_class, agent_name, session in initial_agents:
                self.create_agent(
                    agent_class=agent_class,
                    agent_name=agent_name,
                    workgroup_name=workgroup_name,
                    session=session,
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
        session: AgentSession,
    ) -> BaseAgent:
        """Create and register an agent, creating its workgroup when absent."""
        workgroup = self.workgroups.get(workgroup_name)
        if workgroup is None:
            workgroup = self.create_workgroup(workgroup_name)

        if agent_name in workgroup.agents:
            raise ValueError(
                f"Agent {agent_name!r} already exists in workgroup {workgroup_name!r}."
            )

        agent = agent_class(agent_name, workgroup, session)
        workgroup.agents[agent_name] = agent
        return agent

    def get_agent(self, workgroup_name: str, agent_name: str) -> BaseAgent:
        """Return an existing agent from the named workgroup."""
        return self.workgroups[workgroup_name].agents[agent_name]
