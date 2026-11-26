# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Execution interface and discovery metadata shared by ForeRSI workflows."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph

from fore_rsi.config import AgentConfig, WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import ToolMcpHost
from fore_rsi.rsi_workflows.base_agent import AgentState, BaseAgent
from fore_rsi.rsi_workflows.workflow_runtimes.agent_scheduler import (
    AgentScheduler,
    SchedulingPriority,
)
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

    async def run(self, workspace_id: str) -> None:
        """Prepare, compile, invoke, and clean up one Workflow execution."""
        try:
            workflow = self.build_workflow().compile(checkpointer=InMemorySaver())
            await workflow.ainvoke(
                self.prepare_workflow_input(workspace_id),
                self.workflow_config(),
            )
        finally:
            await self.close_all_agents()

    def build_workflow(self) -> StateGraph:
        """Create this Workflow's graph from its node and edge declarations."""
        # LangGraph stores a plain dict as one root value. Returning a dict replaces
        # the whole state; returning None leaves it unchanged and edges still run.
        graph = StateGraph(dict)
        self.build_workflow_nodes(graph)
        self.build_workflow_edges(graph)
        return graph

    @abstractmethod
    def build_workflow_nodes(self, graph: StateGraph) -> None:
        """Add this Workflow's nodes to the graph."""
        ...

    @abstractmethod
    def build_workflow_edges(self, graph: StateGraph) -> None:
        """Add this Workflow's edges and conditional routes to the graph."""
        ...

    def prepare_workflow_input(self, workspace_id: str) -> dict[str, object]:
        """Return the input passed to a newly started Workflow graph."""
        return {"workspace_id": workspace_id}

    def workflow_config(self) -> dict[str, dict[str, str]]:
        """Return the checkpointer configuration for this Workflow session."""
        return {"configurable": {"thread_id": self.session_directory.name}}

    async def close_all_agents(self) -> None:
        """Close every registered Agent and release its Scheduler reservation."""
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

    async def request_agent_creation(
        self,
        workflow_state: Mapping[str, object],
        *,
        agent_class: type[BaseAgent],
        agent_config: AgentConfig,
        workgroup_name: str | None = None,
        agent_name: str | None = None,
        priority: SchedulingPriority = SchedulingPriority.LOW,
    ) -> dict[str, object]:
        """Return the incoming workflow state with the newly scheduled Agent and its names."""
        workgroup_name = workgroup_name or workflow_state.get("workgroup_name")
        if agent_name is None:
            agent_name = str(
                workflow_state.get("agent_name")
                or self.next_agent_name(agent_class.role_name)
            )
        # Scheduler owns quota admission and creation; Workflow supplies context only.
        agent_fields = await self.agent_scheduler.create_agent(
            agent_class=agent_class,
            agent_name=agent_name,
            workgroup_name=workgroup_name,
            agent_config=agent_config,
            workflow=self,
            workspace_id=str(workflow_state["workspace_id"]),
            is_entry_agent=bool(workflow_state.get("is_entry", False)),
            priority=priority,
        )
        return {**workflow_state, **agent_fields}

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
