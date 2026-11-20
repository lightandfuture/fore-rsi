# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Tool implementations for the default workflow's Coordinator."""

from collections.abc import Awaitable, Callable

from mcp.server.mcpserver.exceptions import ToolError
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import AgentTool
from fore_rsi.rsi_workflows.workflow_runtimes.task import TaskSubmission


def bind_submit_task(
    submit_task_operation: Callable[[TaskSubmission], Awaitable[None]],
) -> AgentTool:
    """Bind the tool to this session's task operation, keeping that dependency out of the MCP schema."""

    async def submit_task(task_submission: TaskSubmission) -> dict[str, object]:
        """Submit the complete task agreed with the user and return the saved revision and its file.

        Include the goal, constraints, agent_team allocations, environment_variables as name/value pairs, and
        task_comments when known. Keep credentials in the host environment instead of the task submission. In
        constraints, preserve common_constraints, resources, stop_conditions, and time_budget. In agent_team,
        declare each role's model, effort, and quota. For updates, submit the complete current task again and
        retain unchanged requirements.
        """
        try:
            await submit_task_operation(task_submission)
        except ValueError as validation_error:
            raise ToolError(str(validation_error)) from validation_error
        return {"task_submission_queued": True}

    return submit_task
