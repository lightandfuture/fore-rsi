# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Shared nodes for task intake, task updates, and branch exits."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from loguru import logger

from fore_rsi.rsi_workflows.base_agent import AgentState
from fore_rsi.rsi_workflows.workflow_runtimes.task import TaskRevision, TaskSubmission

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow

    from ..workflow import DefaultWorkflow


async def wait_for_task_submission(
    workflow: "DefaultWorkflow",
    workflow_state: Mapping[str, object],
) -> dict[str, object]:
    """Consume the next queued Coordinator submission and return it with the existing workflow state."""
    task_submission = await workflow.task_submission_queue.get()
    return {**workflow_state, "task_submission": task_submission}


async def enqueue_task_submission(
    workflow: "DefaultWorkflow",
    task_submission: TaskSubmission,
) -> None:
    """Publish one Coordinator task submission to the Workflow-owned queue."""
    await workflow.task_submission_queue.put(task_submission)


async def update_task_to_agents(workflow: "BaseWorkflow", workflow_state: Mapping[str, object]) -> None:
    """Queue a new task revision's path for all current members, including sleeping ones."""
    if not workflow_state["is_new_task_revision"]:
        return

    revision = cast(TaskRevision, workflow_state["task_revision"])
    message = (
        f"Task revision {revision.revision_number} is available. "
        f"Read {revision.revision_file_path.resolve()} for the updated requirements."
    )
    members = [agent for group in workflow.workgroups.values() for agent in group.agents.values()]
    for agent in members:
        if agent.state not in (AgentState.RETIRED, AgentState.FAILED):
            await agent.send_message(message)


def exit_node(workflow: "BaseWorkflow", workflow_state: Mapping[str, object], *, graph_name: str) -> None:
    """Log the branch exit at WARNING for exhausted attempts, INFO otherwise.

    exit_node --> END[finish]
    """
    if workflow_state.get("tool_submission_status") == "exceed_limit_try":
        logger.warning(
            "Ending branch in graph '{}' (session '{}'): {} exhausted the tool submission attempt limit ({}).",
            graph_name,
            workflow.session_directory.name,
            workflow_state["agent_name"],
            workflow.config.max_attempts,
        )
    else:
        logger.info("Ending branch in graph '{}' (session '{}').", graph_name, workflow.session_directory.name)
