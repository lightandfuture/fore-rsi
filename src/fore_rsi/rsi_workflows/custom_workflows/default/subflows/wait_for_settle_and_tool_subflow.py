# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Shared subflow for waiting on an Agent turn before checking its tool submission."""

from functools import partial
from typing import cast

from langgraph.graph import END, START, StateGraph

from fore_rsi.rsi_workflows.base_agent import BaseAgent


def build_wait_for_settle_and_tool_subflow(*, max_attempts: int) -> StateGraph:
    """Return a subflow whose tool_submission_status selects the caller's A, B, or C.

    The attempt budget includes the initial prompt.

    START --> wait_for_settle --> is_tool_submission
                                     +--[submitted]        --> A
                                     +--[not_submitted]    --> B
                                     +--[exceed_limit_try] --> C
    """
    graph = StateGraph(dict)
    graph.add_node("wait_for_settle", wait_for_settle)
    graph.add_node("is_tool_submission", partial(is_tool_submission, max_attempts=max_attempts))
    graph.add_edge(START, "wait_for_settle")
    graph.add_edge("wait_for_settle", "is_tool_submission")
    graph.add_edge("is_tool_submission", END)
    return graph


async def wait_for_settle(workflow_state: dict[str, object]) -> None:
    """Wait for the active Agent's turn without changing graph state."""
    agent = cast(BaseAgent, workflow_state["agent"])
    await agent.wait_for_settle()


def is_tool_submission(workflow_state: dict[str, object], *, max_attempts: int) -> dict[str, object]:
    """Check the step's expected tool calls after settle; the caller owns routing and tool payloads."""
    agent = cast(BaseAgent, workflow_state["agent"])
    step_tool_calls = agent.step_tool_calls
    if step_tool_calls is None:
        raise RuntimeError("The settled step did not declare its expected tool calls.")

    if step_tool_calls.outcome is None:
        if step_tool_calls.has_expected_tool_calls():
            step_tool_calls.outcome = "submitted"
        elif step_tool_calls.attempt_number >= max_attempts:
            step_tool_calls.outcome = "exceed_limit_try"
        else:
            step_tool_calls.outcome = "not_submitted"
    return {**workflow_state, "tool_submission_status": step_tool_calls.outcome}
