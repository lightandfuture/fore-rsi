# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Inference optimization workflow assembled from domain-specific subflows."""

from functools import partial

from langgraph.graph import END, START, StateGraph

from fore_rsi.config import WorkflowConfig
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator import (
    CoordinatorAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.workflow import DefaultWorkflow
from fore_rsi.rsi_workflows.custom_workflows.inference.workflow_flows.experiment import (
    build_experiment_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.inference.workflow_flows.exploration import (
    build_exploration_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.inference.workflow_flows.initial_explorer import (
    build_initial_explorer_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.inference.workflow_flows.initial_verifier import (
    build_initial_verifier_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.inference.workflow_flows.watchdog import (
    build_watchdog_workflow,
)
from fore_rsi.rsi_workflows.custom_workflows.inference.workflow_flows.work import (
    build_work_workflow,
)


class InferenceWorkflow(DefaultWorkflow):
    """Run the detailed Explorer, Worker, and Verifier loop for inference optimization."""

    workflow_name = "inference"

    def build_workflow_nodes(self, graph: StateGraph) -> None:
        """Add inference task intake, initialization, and area nodes."""
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
        graph.add_node("wait_for_task_submission", self.wait_for_task_submission)
        graph.add_node("publish_task", self.task.publish_task)
        graph.add_node(
            "update_agent_scheduler",
            self.agent_scheduler.update_agent_scheduler,
        )
        graph.add_node("initialize_first_task", lambda workflow_state: {})
        graph.add_node(
            "initialize_explorer_context",
            build_initial_explorer_workflow(self).compile(),
        )
        graph.add_node(
            "initialize_verifier_pool",
            build_initial_verifier_workflow(self).compile(),
        )
        graph.add_node("apply_existing_task_update", lambda workflow_state: {})
        graph.add_node("route_workflow_stage", lambda workflow_state: {})
        graph.add_node(
            "run_exploration_area",
            build_exploration_workflow(self).compile(),
        )
        graph.add_node("run_work_area", build_work_workflow(self).compile())
        graph.add_node(
            "run_experiment_area",
            build_experiment_workflow(self).compile(),
        )
        graph.add_node(
            "run_watchdog_area",
            build_watchdog_workflow(self).compile(),
        )
        graph.add_node("parse_task", CoordinatorAgent.parse_task)

    def build_workflow_edges(self, graph: StateGraph) -> None:
        """Add inference task intake, initialization, area routing, and finish edges."""
        # Edge flow:
        #
        # START -> create_coordinator -> task intake -> update_agent_scheduler
        #                                      |
        #                    +-----------------+------------------+
        #                    |                                    |
        #              first task                          existing task
        #                    |                                    |
        #        initialize_first_task          apply_existing_task_update
        #              +-----------+                         |
        #              |           |                         v
        #              v           v                route_workflow_stage
        # initialize_explorer_context  initialize_verifier_pool
        #              |                       +--> END
        #              v
        #       run_exploration_area                  route_workflow_stage
        #              |                               +--> run_exploration_area
        #              +-------------------------------+--> run_work_area
        #                                              +--> run_experiment_area
        #                                              +--> run_watchdog_area
        #                                              +--> wait_for_task_submission / END
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
                "existing_task": "apply_existing_task_update",
            },
        )
        graph.add_edge("initialize_first_task", "initialize_explorer_context")
        graph.add_edge("initialize_first_task", "initialize_verifier_pool")
        graph.add_edge("initialize_explorer_context", "run_exploration_area")
        graph.add_edge("initialize_verifier_pool", END)
        graph.add_edge("apply_existing_task_update", "route_workflow_stage")
        graph.add_conditional_edges(
            "route_workflow_stage",
            lambda workflow_state: workflow_state.get(
                "next_workflow_stage", "wait_for_task_submission"
            ),
            {
                "exploration": "run_exploration_area",
                "work": "run_work_area",
                "experiment": "run_experiment_area",
                "watchdog": "run_watchdog_area",
                "wait_for_task_submission": "wait_for_task_submission",
                "finish": END,
            },
        )
        graph.add_edge("run_exploration_area", "route_workflow_stage")
        graph.add_edge("run_work_area", "route_workflow_stage")
        graph.add_edge("run_experiment_area", "route_workflow_stage")
        graph.add_edge("run_watchdog_area", "route_workflow_stage")
