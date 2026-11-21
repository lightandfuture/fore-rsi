# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Minimal Watchdog subflow for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_watchdog_workflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Run one generic Watchdog review stage."""
    graph = StateGraph(dict)
    for node_name in (
        "create_watchdog",
        "watchdog_chat",
        "wait_for_stage_completion",
        "watchdog_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_edge(START, "create_watchdog")
    graph.add_edge("create_watchdog", "watchdog_chat")
    graph.add_edge("watchdog_chat", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "watchdog_area_complete")
    graph.add_edge("watchdog_area_complete", END)
    return graph
