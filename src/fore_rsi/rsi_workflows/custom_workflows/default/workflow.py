# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow for general-purpose agent collaboration."""

import asyncio
from collections.abc import Mapping
from functools import partial
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
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
from fore_rsi.rsi_workflows.custom_workflows.default.agents.worker import WorkerAgent
from fore_rsi.rsi_workflows.workflow_runtimes.task import Task, TaskSubmission


class DefaultWorkflow(BaseWorkflow):
    """Coordinate a general-purpose agent team's collaboration."""

    workflow_name = "default"

    # Available roles; each role may have multiple agent instances.
    agent_roles = {
        "Coordinator": CoordinatorAgent,
        "Explorer": ExplorerAgent,
        "Worker": WorkerAgent,
        "Verifier": VerifierAgent,
        "Checker": CheckerAgent,
        "Watchdog": WatchdogAgent,
    }

    def __init__(self, config: WorkflowConfig, session_directory: Path) -> None:
        """Create the workflow state and task history without starting native execution."""
        super().__init__(config, session_directory)
        self.task = Task(session_directory)
        self.default_agent_config = AgentConfig(harness=config.harness_or_default)
        self.task_submission_queue: asyncio.Queue[TaskSubmission] = asyncio.Queue()

    async def run(self, workspace_id: str) -> None:
        """Compile and run the outer workflow, then close its global Agents."""
        try:
            # Restore persisted role quotas before the workflow can request Agents.
            current_task_revision = self.task.current_task
            if current_task_revision is not None:
                await self.agent_scheduler.set_role_quotas(
                    current_task_revision.task_submission.agent_team.roles
                )
            workflow = self.build_workflow().compile(checkpointer=InMemorySaver())
            workflow_config = {"configurable": {"thread_id": self.session_directory.name}}
            await workflow.ainvoke(
                {
                    "workspace_id": workspace_id,
                    "startup_task_file": str(self.config.task)
                    if self.config.task is not None
                    else None,
                },
                workflow_config,
            )
        finally:
            for agent_name in tuple(self.global_workgroup.agents):
                await self.close_agent(WorkflowConfig.GLOBAL_WORKGROUP_NAME, agent_name)

    def build_workflow(self) -> StateGraph:
        """Declare task intake, independent pool initialization, and area routing."""
        # Outer workflow:
        #
        # START -> create_coordinator
        #              |
        #       +------+-----------------------------+
        #       |                                    |
        #   startup task                         interactive session
        #       |                                    |
        #   parse_task                     wait_for_task_submission
        #       +--------------------+---------------+
        #                            |
        #                      publish_task
        #                            |
        #                update_agent_scheduler
        #                 +----------+-----------+
        #                 |                      |
        #             first_task             existing_task
        #                 |                      |
        #      initialize_first_task   apply_existing_task_update
        #          +----------+                    |
        #          |          |                    |
        #          v          v                    v
        #  explorer bootstrap  verifier pool   route_workflow_stage
        #          |          |                    |
        #          |          +--> END             +--> exploration
        #          v                               +--> work
        #  run_exploration_area                    +--> experiment
        #          |                               +--> watchdog
        #          +------------------------------+--> task update / finish
        #
        # Verifier preparation ends independently; only experiment admission waits for its pool.
        graph = StateGraph(dict)
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
            self.build_initial_explorer_workflow().compile(),
        )
        graph.add_node(
            "initialize_verifier_pool",
            self.build_initial_verifier_workflow().compile(),
        )
        graph.add_node("apply_existing_task_update", lambda workflow_state: {})
        graph.add_node("route_workflow_stage", lambda workflow_state: {})
        graph.add_node(
            "run_exploration_area",
            self.build_exploration_workflow().compile(),
        )
        graph.add_node("run_work_area", self.build_work_workflow().compile())
        graph.add_node(
            "run_experiment_area",
            self.build_experiment_workflow().compile(),
        )
        graph.add_node(
            "run_watchdog_area",
            self.build_watchdog_workflow().compile(),
        )
        graph.add_node("parse_task", CoordinatorAgent.parse_task)

        graph.add_edge(START, coordinator_node_name)
        # A startup task is parsed by the Coordinator; an interactive session waits for its tool call.
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

        # Task intake persists the revision and applies its role/model/effort quotas.
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

        # Explorer context can start working immediately. Verifier-pool preparation runs independently
        # and only gates experiment admission, not exploration admission.
        graph.add_edge("initialize_first_task", "initialize_explorer_context")
        graph.add_edge("initialize_first_task", "initialize_verifier_pool")
        graph.add_edge("initialize_explorer_context", "run_exploration_area")
        graph.add_edge("initialize_verifier_pool", END)
        graph.add_edge("apply_existing_task_update", "route_workflow_stage")

        # Area handoffs are selected by work-item and pool events produced by the area graphs.
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
        return graph

    def build_initial_explorer_workflow(self) -> StateGraph:
        """Declare Explorer baseline setup before the active Explorer slots are filled."""
        # Initial Explorer bootstrap; the Verifier bootstrap is an independent outer branch.
        #
        # START
        #   |
        # create_initial_explorer
        #   |
        # study_initial_context
        #   |
        # wait_for_stage_completion -> route_stage_completion
        #   |                              |
        #   |              +---------------+--------------------+
        #   |              |                                    |
        #   |       define_initial_baseline             define_baseline_experiment
        #   |              |                                    |
        #   +--------------+---------- wait_for_stage_completion+
        #                                  |
        #                    register_baseline_candidate
        #                                  |
        #                         fill_explorer_slots
        #                                  |
        #                    exploration_bootstrap_ready -> END
        #
        # fill_explorer_slots starts independent Explorer work items; it does not wait for Verifier.
        workflow = StateGraph(dict)
        for node_name in (
            "define_initial_baseline",
            "define_baseline_experiment",
            "register_baseline_candidate",
            "fill_explorer_slots",
            "exploration_bootstrap_ready",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})
        workflow.add_node(
            "create_initial_explorer",
            partial(
                self.request_agent_creation,
                agent_class=ExplorerAgent,
                agent_config=self.default_agent_config,
            ),
        )
        workflow.add_node(
            "study_initial_context",
            ExplorerAgent.study_initial_context,
        )
        workflow.add_node("wait_for_stage_completion", lambda workflow_state: {})
        workflow.add_node("route_stage_completion", lambda workflow_state: {})

        workflow.add_edge(START, "create_initial_explorer")
        workflow.add_edge("create_initial_explorer", "study_initial_context")
        workflow.add_edge("study_initial_context", "wait_for_stage_completion")
        workflow.add_edge("wait_for_stage_completion", "route_stage_completion")
        workflow.add_conditional_edges(
            "route_stage_completion",
            lambda workflow_state: workflow_state.get(
                "explorer_stage_route", "define_initial_baseline"
            ),
            {
                "define_initial_baseline": "define_initial_baseline",
                "define_baseline_experiment": "define_baseline_experiment",
                "register_baseline_candidate": "register_baseline_candidate",
                "fill_explorer_slots": "fill_explorer_slots",
                "exploration_bootstrap_ready": "exploration_bootstrap_ready",
            },
        )
        workflow.add_edge("define_initial_baseline", "wait_for_stage_completion")
        workflow.add_edge("define_baseline_experiment", "wait_for_stage_completion")
        workflow.add_edge("register_baseline_candidate", "fill_explorer_slots")
        workflow.add_edge("fill_explorer_slots", "exploration_bootstrap_ready")
        workflow.add_edge("exploration_bootstrap_ready", END)
        return workflow

    def build_initial_verifier_workflow(self) -> StateGraph:
        """Declare background Verifier-pool preparation without blocking Explorer work."""
        # Verifier bootstrap runs beside Explorer bootstrap:
        #
        # START -> create_initial_verifier -> study_verifier_context
        #                                  |
        #                         wait_for_stage_completion
        #                                  |
        #                         route_stage_completion
        #                                  |
        #                  prepare_verifier_resources
        #                                  |
        #                         wait_for_stage_completion
        #                                  |
        #                         route_stage_completion
        #                                  |
        #                         fill_verifier_slots
        #                                  |
        #                       confirm_verifier_context
        #                                  |
        #                         verifier_pool_ready -> END
        #
        # A candidate waits at wait_for_verifier_slot later if this pool is not ready yet.
        workflow = StateGraph(dict)
        for node_name in (
            "prepare_verifier_resources",
            "fill_verifier_slots",
            "confirm_verifier_context",
            "verifier_pool_ready",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})
        workflow.add_node(
            "create_initial_verifier",
            partial(
                self.request_agent_creation,
                agent_class=VerifierAgent,
                agent_config=self.default_agent_config,
            ),
        )
        workflow.add_node("study_verifier_context", lambda workflow_state: {})
        workflow.add_node("wait_for_stage_completion", lambda workflow_state: {})
        workflow.add_node("route_stage_completion", lambda workflow_state: {})

        workflow.add_edge(START, "create_initial_verifier")
        workflow.add_edge("create_initial_verifier", "study_verifier_context")
        workflow.add_edge("study_verifier_context", "wait_for_stage_completion")
        workflow.add_edge("wait_for_stage_completion", "route_stage_completion")
        workflow.add_conditional_edges(
            "route_stage_completion",
            lambda workflow_state: workflow_state.get(
                "verifier_stage_route", "prepare_verifier_resources"
            ),
            {
                "prepare_verifier_resources": "prepare_verifier_resources",
                "fill_verifier_slots": "fill_verifier_slots",
                "verifier_pool_ready": "verifier_pool_ready",
            },
        )
        workflow.add_edge("prepare_verifier_resources", "wait_for_stage_completion")
        workflow.add_edge("fill_verifier_slots", "confirm_verifier_context")
        workflow.add_edge("confirm_verifier_context", "verifier_pool_ready")
        workflow.add_edge("verifier_pool_ready", END)
        return workflow

    def build_exploration_workflow(self) -> StateGraph:
        """Declare one dynamic Explorer work item from slot admission to Proposal handoff."""
        workflow = StateGraph(dict)
        for node_name in (
            "dispatch_explorer_work",
            "explore_direction",
            "create_checker",
            "check_exploration",
            "create_proposal",
            "check_proposal",
            "publish_proposal",
            "queue_worker_request",
            "queue_experiment_request",
            "suspend_explorer",
            "release_explorer_slot",
            "retire_explorer",
            "finish_exploration",
            "route_exploration_decision",
            "route_proposal_decision",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})
        workflow.add_node("wait_for_stage_completion", lambda workflow_state: {})
        workflow.add_node("route_stage_completion", lambda workflow_state: {})

        workflow.add_edge(START, "dispatch_explorer_work")
        workflow.add_edge("dispatch_explorer_work", "explore_direction")
        workflow.add_edge("explore_direction", "wait_for_stage_completion")
        workflow.add_edge("create_checker", "check_exploration")
        workflow.add_edge("check_exploration", "wait_for_stage_completion")
        workflow.add_edge("create_proposal", "wait_for_stage_completion")
        workflow.add_edge("check_proposal", "wait_for_stage_completion")
        workflow.add_edge("wait_for_stage_completion", "route_stage_completion")
        workflow.add_conditional_edges(
            "route_stage_completion",
            lambda workflow_state: workflow_state.get(
                "exploration_stage_route", "create_checker"
            ),
            {
                "create_checker": "create_checker",
                "check_exploration": "check_exploration",
                "route_exploration_decision": "route_exploration_decision",
                "create_proposal": "create_proposal",
                "check_proposal": "check_proposal",
                "route_proposal_decision": "route_proposal_decision",
            },
        )
        workflow.add_conditional_edges(
            "route_exploration_decision",
            lambda workflow_state: workflow_state.get(
                "exploration_decision", "create_proposal"
            ),
            {
                "create_proposal": "create_proposal",
                "continue_exploration": "explore_direction",
                "finish_exploration": "finish_exploration",
            },
        )
        workflow.add_conditional_edges(
            "route_proposal_decision",
            lambda workflow_state: workflow_state.get(
                "proposal_decision", "publish_proposal"
            ),
            {
                "publish_proposal": "publish_proposal",
                "revise_exploration": "explore_direction",
                "request_experiment": "queue_experiment_request",
            },
        )
        workflow.add_edge("publish_proposal", "queue_worker_request")
        workflow.add_edge("queue_worker_request", "release_explorer_slot")
        workflow.add_edge("queue_experiment_request", "release_explorer_slot")
        workflow.add_edge("release_explorer_slot", "suspend_explorer")
        workflow.add_edge("suspend_explorer", END)
        workflow.add_edge("finish_exploration", "retire_explorer")
        workflow.add_edge("retire_explorer", END)
        return workflow

    def build_work_workflow(self) -> StateGraph:
        """Declare one Worker work item from Proposal admission to Candidate handoff."""
        workflow = StateGraph(dict)
        for node_name in (
            "dispatch_worker_work",
            "receive_proposal",
            "implement_candidate",
            "check_implementation",
            "publish_candidate",
            "queue_experiment_request",
            "return_to_explorer",
            "release_worker_slot",
            "route_implementation_decision",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})
        workflow.add_node("wait_for_stage_completion", lambda workflow_state: {})
        workflow.add_node("route_stage_completion", lambda workflow_state: {})

        workflow.add_edge(START, "dispatch_worker_work")
        workflow.add_edge("dispatch_worker_work", "receive_proposal")
        workflow.add_edge("receive_proposal", "implement_candidate")
        workflow.add_edge("implement_candidate", "wait_for_stage_completion")
        workflow.add_edge("check_implementation", "wait_for_stage_completion")
        workflow.add_edge("wait_for_stage_completion", "route_stage_completion")
        workflow.add_conditional_edges(
            "route_stage_completion",
            lambda workflow_state: workflow_state.get(
                "implementation_stage_route", "check_implementation"
            ),
            {
                "check_implementation": "check_implementation",
                "route_implementation_decision": "route_implementation_decision",
            },
        )
        workflow.add_conditional_edges(
            "route_implementation_decision",
            lambda workflow_state: workflow_state.get(
                "implementation_decision", "publish_candidate"
            ),
            {
                "publish_candidate": "publish_candidate",
                "revise_implementation": "implement_candidate",
                "request_experiment": "queue_experiment_request",
                "return_to_explorer": "return_to_explorer",
            },
        )
        workflow.add_edge("publish_candidate", "queue_experiment_request")
        workflow.add_edge("queue_experiment_request", "release_worker_slot")
        workflow.add_edge("return_to_explorer", "release_worker_slot")
        workflow.add_edge("release_worker_slot", END)
        return workflow

    def build_experiment_workflow(self) -> StateGraph:
        """Declare Verifier admission, experiment execution, result recording, and feedback."""
        workflow = StateGraph(dict)
        for node_name in (
            "dispatch_experiment_work",
            "wait_for_verifier_slot",
            "create_or_resume_verifier",
            "prepare_experiment",
            "wait_for_experiment_resources",
            "run_experiment",
            "verify_result",
            "record_experiment_result",
            "publish_report",
            "publish_feedback",
            "release_verifier_slot",
            "route_verification_decision",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})
        workflow.add_node("wait_for_stage_completion", lambda workflow_state: {})
        workflow.add_node("route_stage_completion", lambda workflow_state: {})

        workflow.add_edge(START, "dispatch_experiment_work")
        workflow.add_edge("dispatch_experiment_work", "wait_for_verifier_slot")
        workflow.add_edge("wait_for_verifier_slot", "create_or_resume_verifier")
        workflow.add_edge("create_or_resume_verifier", "prepare_experiment")
        workflow.add_edge("prepare_experiment", "wait_for_experiment_resources")
        workflow.add_edge("wait_for_experiment_resources", "run_experiment")
        workflow.add_edge("run_experiment", "wait_for_stage_completion")
        workflow.add_edge("verify_result", "wait_for_stage_completion")
        workflow.add_edge("wait_for_stage_completion", "route_stage_completion")
        workflow.add_conditional_edges(
            "route_stage_completion",
            lambda workflow_state: workflow_state.get(
                "experiment_stage_route", "verify_result"
            ),
            {
                "verify_result": "verify_result",
                "route_verification_decision": "route_verification_decision",
            },
        )
        workflow.add_conditional_edges(
            "route_verification_decision",
            lambda workflow_state: workflow_state.get(
                "verification_decision", "publish_experiment_result"
            ),
            {
                "publish_experiment_result": "record_experiment_result",
                "retry_experiment": "prepare_experiment",
                "return_feedback": "publish_feedback",
            },
        )
        workflow.add_edge("record_experiment_result", "publish_report")
        workflow.add_edge("publish_report", "release_verifier_slot")
        workflow.add_edge("publish_feedback", "release_verifier_slot")
        workflow.add_edge("release_verifier_slot", END)
        return workflow

    def build_watchdog_workflow(self) -> StateGraph:
        """Declare periodic Watchdog review, reminders, and progress publication."""
        workflow = StateGraph(dict)
        for node_name in (
            "create_watchdog",
            "collect_progress",
            "review_progress",
            "send_reminders",
            "publish_watchdog_report",
            "route_watchdog_decision",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})
        workflow.add_node("wait_for_stage_completion", lambda workflow_state: {})
        workflow.add_node("route_stage_completion", lambda workflow_state: {})

        workflow.add_edge(START, "create_watchdog")
        workflow.add_edge("create_watchdog", "collect_progress")
        workflow.add_edge("collect_progress", "review_progress")
        workflow.add_edge("review_progress", "wait_for_stage_completion")
        workflow.add_edge("wait_for_stage_completion", "route_stage_completion")
        workflow.add_conditional_edges(
            "route_stage_completion",
            lambda workflow_state: workflow_state.get(
                "watchdog_stage_route", "route_watchdog_decision"
            ),
            {"route_watchdog_decision": "route_watchdog_decision"},
        )
        workflow.add_conditional_edges(
            "route_watchdog_decision",
            lambda workflow_state: workflow_state.get(
                "watchdog_decision", "publish_watchdog_report"
            ),
            {
                "publish_watchdog_report": "publish_watchdog_report",
                "send_reminders": "send_reminders",
                "continue_watchdog": "collect_progress",
            },
        )
        workflow.add_edge("send_reminders", "collect_progress")
        workflow.add_edge("publish_watchdog_report", END)
        return workflow

    async def wait_for_task_submission(
        self, workflow_state: Mapping[str, object]
    ) -> dict[str, object]:
        """Wait for and consume the next Coordinator task submission."""
        return {"task_submission": await self.task_submission_queue.get()}

    async def enqueue_task_submission(self, task_submission: TaskSubmission) -> None:
        """Queue a Coordinator task submission for the next workflow boundary."""
        await self.task_submission_queue.put(task_submission)
