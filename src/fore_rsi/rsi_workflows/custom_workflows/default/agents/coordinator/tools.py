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
        """Convert the user's requirements into a complete task declaration for the team.

        Make reasonable assumptions and fill optional details from the available context. Ask for clarification only
        when ambiguity would materially change the goal, evaluation, safety, or resource budget. Include the goal,
        constraints, agent_team allocations,
        environment_variables as name/value pairs, and task_comments when known. Keep credentials in the host
        environment instead of the task declaration. In constraints, preserve common_constraints, resources,
        stop_conditions, and time_budget. In agent_team, declare each role's model, effort, and quota. For updates,
        provide the complete current task again and retain unchanged requirements. The Workflow assigns the revision
        number and persists the accepted declaration.
        """
        try:
            await submit_task_operation(task_submission)
        except ValueError as validation_error:
            raise ToolError(str(validation_error)) from validation_error
        return {"task_submission_queued": True}

    return submit_task
