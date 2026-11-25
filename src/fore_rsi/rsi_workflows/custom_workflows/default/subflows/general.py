# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""General task-intake nodes shared by concrete workflow variants."""

from collections.abc import Mapping
from typing import TYPE_CHECKING

from fore_rsi.rsi_workflows.workflow_runtimes.task import TaskSubmission

if TYPE_CHECKING:
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
