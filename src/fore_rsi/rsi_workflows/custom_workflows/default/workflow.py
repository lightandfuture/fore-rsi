# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow entry point and general-purpose collaboration stages."""

import asyncio
from functools import partial
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from fore_rsi.config import AgentConfig, WorkflowConfig
from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow
from fore_rsi.rsi_workflows.custom_workflows.default.agents.checker import CheckerAgent
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator import (
    CoordinatorAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.explorer import ExplorerAgent
from fore_rsi.rsi_workflows.custom_workflows.default.agents.verifier import (
    VerifierAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.watchdog import (
    WatchdogAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.experiment_workflow import (
    build_experiment_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.exploration_workflow import (
    build_exploration_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.initial_verifier_workflow import (
    build_initial_verifier_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.general import (
    wait_for_task_submission,
)
from fore_rsi.rsi_workflows.workflow_runtimes.task import Task, TaskSubmission


class DefaultWorkflow(BaseWorkflow):
    """Run a general-purpose team workflow for tasks such as inference optimization."""

    workflow_name = "default"

    agent_roles = {
        "Coordinator": CoordinatorAgent,
        "Explorer": ExplorerAgent,
        "Verifier": VerifierAgent,
        "Checker": CheckerAgent,
        "Watchdog": WatchdogAgent,
    }

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
        graph.add_node(
            "wait_for_task_submission",
            partial(wait_for_task_submission, self),
        )
        graph.add_node("publish_task", self.task.publish_task)
        graph.add_node(
            "update_agent_scheduler",
            self.agent_scheduler.update_agent_scheduler,
        )
        graph.add_node("initialize_first_task", lambda workflow_state: {})
        graph.add_node(
            "initialize_verifier_pool",
            build_initial_verifier_workflow(self).compile(),
        )
        graph.add_node("update_task_context", lambda workflow_state: {})
        graph.add_node("route_workflow_stage", lambda workflow_state: {})
        graph.add_node(
            "run_exploration_area",
            build_default_exploration_workflow(self).compile(),
        )
        graph.add_node(
            "run_experiment_area",
            build_default_experiment_workflow(self).compile(),
        )
        graph.add_node("parse_task", CoordinatorAgent.parse_task)

    def build_workflow_edges(self, graph: StateGraph) -> None:
        """Add task intake, initialization, area routing, and finish edges."""
        #
        # START -> create_coordinator
        #              +--[have_task]--------> parse_task --+
        #              |                                    |
        #              +--[await_user_input]-> wait_for_task_submission
        #                                                   |
        #                                             publish_task
        #                                                   |
        #                                         update_agent_scheduler
        coordinator_node_name = f"create_{CoordinatorAgent.role_name.lower()}"
        graph.add_edge(START, coordinator_node_name)
        graph.add_conditional_edges(
            coordinator_node_name,
            lambda workflow_state: "have_task"
            if self.config.task is not None
            else "await_user_input",
            {
                "have_task": "parse_task",
                "await_user_input": "wait_for_task_submission",
            },
        )
        graph.add_edge("parse_task", "wait_for_task_submission")
        graph.add_edge("wait_for_task_submission", "publish_task")
        graph.add_edge("publish_task", "update_agent_scheduler")

        graph.add_conditional_edges(
            "update_agent_scheduler",
            lambda workflow_state: (
                "first_task"
                if workflow_state.get("is_first_task_submission", False)
                else "existing_task"
            ),
            {
                "first_task": "initialize_first_task",
                "existing_task": "update_task_context",
            },
        )

        # update_agent_scheduler
        #       +--[first_task]----> initialize_first_task
        #       |                         +--> run_exploration_area
        #       |                         +--> initialize_verifier_pool -> END
        #       +--[existing_task]-> update_task_context
        #                                      +--> wait_for_task_submission
        graph.add_edge("initialize_first_task", "run_exploration_area")
        graph.add_edge("initialize_first_task", "initialize_verifier_pool")
        graph.add_edge("initialize_verifier_pool", END)
        graph.add_edge("update_task_context", "wait_for_task_submission")

        # run_exploration_area --+
        # run_work_area ---------+
        # run_experiment_area ---+--> route_workflow_stage
        #                                  |
        # route_workflow_stage             |
        #       +--[exploration] -> run_exploration_area
        #       +--[experiment]   -> run_experiment_area
        #       +--[wait_for_task_submission]
        #       +--[finish]       -> END
        graph.add_conditional_edges(
            "route_workflow_stage",
            lambda workflow_state: workflow_state.get(
                "next_workflow_stage", "wait_for_task_submission"
            ),
            {
                "exploration": "run_exploration_area",
                "experiment": "run_experiment_area",
                "wait_for_task_submission": "wait_for_task_submission",
                "finish": END,
            },
        )
        graph.add_edge("run_exploration_area", "route_workflow_stage")
        graph.add_edge("run_experiment_area", "route_workflow_stage")
