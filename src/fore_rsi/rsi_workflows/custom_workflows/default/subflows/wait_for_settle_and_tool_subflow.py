# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Shared subflow for waiting on an Agent turn before checking its tool submission."""

from typing import cast

from langgraph.graph import START, StateGraph

from fore_rsi.rsi_workflows.base_agent import BaseAgent


def build_wait_for_settle_and_tool_subflow() -> StateGraph:
    """Build the turn boundary shared by task intake and the role subflows.

    START --> wait_for_settle --> is_tool_submission
                                     +--[submitted]        --> A
                                     +--[not_submitted]    --> B
                                     +--[exceed_limit_try] --> C
    """
    graph = StateGraph(dict)
    graph.add_node("wait_for_settle", wait_for_settle)
    graph.add_edge(START, "wait_for_settle")
    return graph


async def wait_for_settle(workflow_state: dict[str, object]) -> None:
    """Wait for the active Agent's turn without changing graph state."""
    agent = cast(BaseAgent, workflow_state["agent"])
    await agent.agent_runtime.wait_for_settle()
