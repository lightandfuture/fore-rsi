# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Shared Agent turn boundary nodes for default workflow subflows."""

from collections.abc import Mapping

from fore_rsi.rsi_workflows.base_agent import BaseAgent


async def wait_for_settle(
    workflow_state: Mapping[str, object],
) -> dict[str, object]:
    """Wait for the active Agent's submitted native turn to settle.

    wait_for_settle
        --> is_tool_submission
        +--[submitted]       --> A
        +--[not_submitted]   --> B
        +--[exceed_limit_try] --> caller-owned terminal path
    """
    agent = workflow_state.get("agent")
    if not isinstance(agent, BaseAgent):
        raise TypeError("Workflow state does not contain an active Agent.")
    await agent.agent_runtime.wait_for_settle()
    return {}
