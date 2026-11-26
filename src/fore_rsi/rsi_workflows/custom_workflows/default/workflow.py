# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow entry point and general-purpose collaboration stages."""

import asyncio
from functools import partial
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from fore_rsi.config import AgentConfig, WorkflowConfig
from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator import (
    CoordinatorAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.experiment_subflow import (
    build_experiment_subflow,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.exploration_subflow import (
    build_exploration_subflow,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.general import (
    exit_node,
    update_task_to_agents,
    wait_for_task_submission,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.wait_for_settle_and_tool_subflow import (
    build_wait_for_settle_and_tool_subflow,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.watchdog_subflow import (
    build_watchdog_subflow,
)
from fore_rsi.rsi_workflows.workflow_runtimes.task import Task, TaskSubmission


class DefaultWorkflow(BaseWorkflow):
    """Run a general-purpose team workflow for tasks such as inference optimization."""

    workflow_name = "default"

    agent_roles = {"Coordinator": CoordinatorAgent}

    def __init__(self, config: WorkflowConfig, session_directory: Path) -> None:
        """Create task intake state without starting native Agent execution."""
        super().__init__(config, session_directory)
        self.task = Task(session_directory)
        self.default_agent_config = AgentConfig(harness=config.harness_or_default)
        self.task_submission_queue: asyncio.Queue[TaskSubmission] = asyncio.Queue()

    def prepare_workflow_input(self, workspace_id: str) -> dict[str, object]:
        """Provide workspace and optional startup-task input to a new graph run."""
        return {
            "workspace_id": workspace_id,
            "startup_task_file": (
                str(self.config.task) if self.config.task is not None else None
            ),
        }

    def build_workflow_nodes(self, graph: StateGraph) -> None:
        """Add task intake, initialization, and generic area nodes."""
        coordinator_node_name = f"create_{CoordinatorAgent.role_name.lower()}"
        graph.add_node(
            coordinator_node_name,
            partial(
                self.request_agent_creation,
                agent_class=CoordinatorAgent,
                agent_config=self.default_agent_config,
                workgroup_name=WorkflowConfig.GLOBAL_WORKGROUP_NAME,
            ),
        )
        graph.add_node("parse_task", CoordinatorAgent.parse_task)
        graph.add_node(
            "wait_for_settle_and_tool_subflow",
            build_wait_for_settle_and_tool_subflow(max_attempts=self.config.max_attempts).compile(),
        )
        graph.add_node("wait_for_task_submission", partial(wait_for_task_submission, self))
        graph.add_node("publish_task", self.task.publish_task)
        graph.add_node("update_agent_scheduler", self.agent_scheduler.update_agent_scheduler)
        graph.add_node("update_task_to_agents", partial(update_task_to_agents, self))

        # On entry, LangGraph invokes the returned subgraph with the incoming state.
        graph.add_node("run_exploration_area", lambda _: build_exploration_subflow(self).compile())
        graph.add_node("run_experiment_area", lambda _: build_experiment_subflow(self).compile())
        graph.add_node("run_watchdog_area", lambda _: build_watchdog_subflow(self).compile())
        graph.add_node("exit_node", partial(exit_node, self, graph_name=self.workflow_name))

    def build_workflow_edges(self, graph: StateGraph) -> None:
        """Add task intake, initialization, area routing, and finish edges.

        START --> create_coordinator
                     +--[have_task] ----> parse_task
                     |                    --> wait_for_settle_and_tool_subflow[A=wait_for_task_submission,B=parse_task,C=exit_node]
                     +--[not_have_task] -> wait_for_task_submission
                                              --> publish_task
                                              --> wait_for_task_submission

        publish_task --> update_agent_scheduler
                           +--[initialize]--+--> run_exploration_area
                           |                +--> run_experiment_area
                           |                +--> run_watchdog_area
                           +--[update_task]----> update_task_to_agents --> wait_for_task_submission

        run_exploration_area: update_code_pool           --[Command.PARENT]--> route_workflow_stage[experiment]
        run_experiment_area:  queue_exploration_feedback --[Command.PARENT]--> route_workflow_stage[exploration]

        route_workflow_stage
              +--[exploration] -> run_exploration_area
              +--[experiment] -> run_experiment_area
              +--[watchdog] -> run_watchdog_area
              +--[wait_for_task_submission]
              +--[finish]       -> exit_node

        exit_node --> END
        """
        coordinator_node_name = f"create_{CoordinatorAgent.role_name.lower()}"
        graph.add_edge(START, coordinator_node_name)
        graph.add_conditional_edges(
            coordinator_node_name,
            lambda state: "have_task" if state["startup_task_file"] is not None else "not_have_task",
            {"have_task": "parse_task", "not_have_task": "wait_for_task_submission"},
        )
        graph.add_edge("parse_task", "wait_for_settle_and_tool_subflow")
        graph.add_conditional_edges(
            "wait_for_settle_and_tool_subflow",
            lambda state: state["tool_submission_status"],
            {
                "submitted": "wait_for_task_submission",
                "not_submitted": "parse_task",
                "exceed_limit_try": "exit_node",
            },
        )
        graph.add_edge("wait_for_task_submission", "publish_task")
        graph.add_edge("publish_task", "wait_for_task_submission")
        graph.add_edge("publish_task", "update_agent_scheduler")

        # On first publication, start all three areas in parallel.
        graph.add_conditional_edges(
            "update_agent_scheduler",
            lambda state: ["exploration", "experiment", "watchdog"]
            if state["is_first_task_submission"] else "update_task",
            path_map={
                "exploration": "run_exploration_area",
                "experiment": "run_experiment_area",
                "watchdog": "run_watchdog_area",
                "update_task": "update_task_to_agents",
            },
        )
        graph.add_edge("update_task_to_agents", "wait_for_task_submission")
        graph.add_edge("exit_node", END)
