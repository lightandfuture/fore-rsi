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
from fore_rsi.rsi_workflows.custom_workflows.default.agents.explorer import (
    ExplorerAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.explorer.workflow import (
    study_initial_context,
)
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
        """Declare the outer task, work-area, and Watchdog workflow topology."""
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
        graph.add_node(
            "initialize_first_task",
            self.build_initial_task_workflow().compile(),
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
        # create_coordinator
        # ├── startup task file    -> parse_task -> wait_for_task_submission
        # └── no startup task file -> wait_for_task_submission
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

        # Task intake: save the declaration, apply quotas, then split first setup from later updates.
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
        graph.add_edge("initialize_first_task", "route_workflow_stage")
        graph.add_edge("apply_existing_task_update", "route_workflow_stage")

        # Work-area router: implementations will select the next area from workflow state.
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
            },
        )
        graph.add_edge("run_exploration_area", "route_workflow_stage")
        graph.add_edge("run_work_area", "route_workflow_stage")
        graph.add_edge("run_experiment_area", "route_workflow_stage")
        graph.add_edge("run_watchdog_area", "route_workflow_stage")
        return graph

    def build_initial_task_workflow(self) -> StateGraph:
        """Declare parallel first-time Explorer and Verifier initialization."""
        workflow = StateGraph(dict)
        for node_name in (
            "define_initial_baseline",
            "define_baseline_experiment",
            "register_baseline_candidate",
            "fork_additional_explorers",
            "create_initial_verifier",
            "study_verifier_context",
            "prepare_verifier_resources",
            "fork_verifier_pool",
            "confirm_verifier_context",
            "sleep_verifier",
            "initial_task_ready",
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

        # START
        # ├── create_initial_explorer -> study_initial_context -> define_initial_baseline
        # │   -> define_baseline_experiment -> register_baseline_candidate
        # │   -> fork_additional_explorers
        # └── create_initial_verifier -> study_verifier_context -> prepare_verifier_resources
        #     -> fork_verifier_pool -> confirm_verifier_context -> sleep_verifier
        workflow.add_edge(START, "create_initial_explorer")
        workflow.add_edge(START, "create_initial_verifier")

        # Initial Explorer path: create normally, then establish the baseline before forking more Explorers.
        workflow.add_edge("create_initial_explorer", "study_initial_context")
        workflow.add_edge("study_initial_context", "define_initial_baseline")
        workflow.add_edge(
            "define_initial_baseline", "define_baseline_experiment"
        )
        workflow.add_edge(
            "define_baseline_experiment", "register_baseline_candidate"
        )
        workflow.add_edge(
            "register_baseline_candidate", "fork_additional_explorers"
        )
        workflow.add_edge("fork_additional_explorers", "initial_task_ready")

        # Initial Verifier path runs in parallel with the initial Explorer path.
        workflow.add_edge("create_initial_verifier", "study_verifier_context")
        workflow.add_edge(
            "study_verifier_context", "prepare_verifier_resources"
        )
        workflow.add_edge(
            "prepare_verifier_resources", "fork_verifier_pool"
        )
        workflow.add_edge(
            "fork_verifier_pool", "confirm_verifier_context"
        )
        workflow.add_edge("confirm_verifier_context", "sleep_verifier")
        # fork_additional_explorers and sleep_verifier -> initial_task_ready
        workflow.add_edge("sleep_verifier", "initial_task_ready")
        workflow.add_edge("initial_task_ready", END)
        return workflow

    def build_exploration_workflow(self) -> StateGraph:
        """Declare the exploration area from direction discovery to proposal handoff."""
        workflow = StateGraph(dict)
        for node_name in (
            "explore_direction",
            "create_checker",
            "check_exploration",
            "create_proposal",
            "check_proposal",
            "publish_proposal",
            "request_experiment",
            "finish_exploration",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})

        workflow.add_edge(START, "explore_direction")
        workflow.add_edge("explore_direction", "create_checker")
        workflow.add_edge("create_checker", "check_exploration")
        workflow.add_conditional_edges(
            "check_exploration",
            lambda workflow_state: workflow_state.get(
                "exploration_decision", "create_proposal"
            ),
            {
                "create_proposal": "create_proposal",
                "continue_exploration": "explore_direction",
                "finish_exploration": "finish_exploration",
            },
        )
        workflow.add_edge("create_proposal", "check_proposal")
        workflow.add_conditional_edges(
            "check_proposal",
            lambda workflow_state: workflow_state.get(
                "proposal_decision", "publish_proposal"
            ),
            {
                "publish_proposal": "publish_proposal",
                "revise_exploration": "explore_direction",
                "request_experiment": "request_experiment",
            },
        )
        workflow.add_edge("publish_proposal", END)
        workflow.add_edge("request_experiment", END)
        workflow.add_edge("finish_exploration", END)
        return workflow

    def build_work_workflow(self) -> StateGraph:
        """Declare the work area from an accepted proposal to an executable candidate."""
        workflow = StateGraph(dict)
        for node_name in (
            "create_worker",
            "receive_proposal",
            "implement_candidate",
            "check_implementation",
            "publish_candidate",
            "request_experiment",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})

        workflow.add_edge(START, "create_worker")
        workflow.add_edge("create_worker", "receive_proposal")
        workflow.add_edge("receive_proposal", "implement_candidate")
        workflow.add_edge("implement_candidate", "check_implementation")
        workflow.add_conditional_edges(
            "check_implementation",
            lambda workflow_state: workflow_state.get(
                "implementation_decision", "publish_candidate"
            ),
            {
                "publish_candidate": "publish_candidate",
                "revise_implementation": "implement_candidate",
                "request_experiment": "request_experiment",
            },
        )
        workflow.add_edge("publish_candidate", END)
        workflow.add_edge("request_experiment", END)
        return workflow

    def build_experiment_workflow(self) -> StateGraph:
        """Declare the experiment area from execution request to verified result."""
        workflow = StateGraph(dict)
        for node_name in (
            "create_experimenter",
            "prepare_experiment",
            "run_experiment",
            "create_verifier",
            "verify_result",
            "publish_experiment_result",
            "return_experiment_feedback",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})

        workflow.add_edge(START, "create_experimenter")
        workflow.add_edge("create_experimenter", "prepare_experiment")
        workflow.add_edge("prepare_experiment", "run_experiment")
        workflow.add_edge("run_experiment", "create_verifier")
        workflow.add_edge("create_verifier", "verify_result")
        workflow.add_conditional_edges(
            "verify_result",
            lambda workflow_state: workflow_state.get(
                "verification_decision", "publish_experiment_result"
            ),
            {
                "publish_experiment_result": "publish_experiment_result",
                "retry_experiment": "run_experiment",
                "return_feedback": "return_experiment_feedback",
            },
        )
        workflow.add_edge("publish_experiment_result", END)
        workflow.add_edge("return_experiment_feedback", END)
        return workflow

    def build_watchdog_workflow(self) -> StateGraph:
        """Declare the Watchdog area for progress review and workflow feedback."""
        workflow = StateGraph(dict)
        for node_name in (
            "create_watchdog",
            "collect_progress",
            "review_progress",
            "send_reminders",
            "publish_watchdog_report",
        ):
            workflow.add_node(node_name, lambda workflow_state: {})

        workflow.add_edge(START, "create_watchdog")
        workflow.add_edge("create_watchdog", "collect_progress")
        workflow.add_edge("collect_progress", "review_progress")
        workflow.add_conditional_edges(
            "review_progress",
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

    async def study_initial_context(
        self, workflow_state: Mapping[str, object]
    ) -> dict[str, object]:
        """Run ExplorerAgent's initial context study stage for the graph node."""
        explorer = self.workgroups[workflow_state["workgroup_name"]].agents[
            workflow_state["agent_name"]
        ]
        await explorer.study_initial_context(workflow_state)
        return {}
