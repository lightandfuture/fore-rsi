# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Task submission tools available to the default workflow's Coordinator."""

from collections.abc import Awaitable, Callable

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentTool
from fore_rsi.rsi_workflows.custom_workflows.default.task import TaskDefinition


def create_coordinator_tools(
    submit_task: Callable[[TaskDefinition], Awaitable[dict[str, object]]],
) -> tuple[AgentTool, ...]:
    """Bind the Coordinator's task-submission tool to its owning workflow."""
    return (
        AgentTool(
            name="submit_task",
            description=(
                "Submit the complete task agreed with the user. Include its goal, constraints, "
                "authorized resources, inputs, deliverables, time budget, and requested team when known. "
                "To revise a task, submit the full declaration including unchanged requirements."
            ),
            handler=submit_task,
        ),
    )
