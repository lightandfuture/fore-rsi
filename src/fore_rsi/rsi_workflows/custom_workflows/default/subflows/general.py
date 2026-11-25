# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Shared nodes for task intake and branch exits."""

from collections.abc import Mapping
from typing import TYPE_CHECKING

from loguru import logger

from fore_rsi.rsi_workflows.workflow_runtimes.task import TaskSubmission

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
