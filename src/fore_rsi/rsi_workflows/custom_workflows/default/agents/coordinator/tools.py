# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Coordinator tools for configuring the default workflow's team."""

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentTool
from fore_rsi.rsi_workflows.workflow_runtimes.agent_scheduler import AgentScheduler, QuotaLimit


def create_tools(agent_scheduler: AgentScheduler) -> tuple[AgentTool, ...]:
    """Bind Coordinator tools to the workflow's shared scheduler during agent construction."""

    async def set_quota(role_name: str, model: str, limit: QuotaLimit) -> dict[str, object]:
        """Apply one role/model limit and return its current configuration to the Coordinator."""
        quota = agent_scheduler.set_quota(role_name, model, limit)
        return {
            "role_name": quota.agent_class.role_name,
            "model": quota.model,
            "limit": quota.limit,
        }

    return (
        AgentTool(
            name="set_quota",
            description=(
                "Set or update a role's concurrent execution limit for one model. "
                "Use a positive integer, 0 to disable new dispatches, or 'unlimited' to remove the cap. "
                f"Available roles: {', '.join(role.role_name for role in agent_scheduler.agent_roles)}."
            ),
            handler=set_quota,
        ),
    )
