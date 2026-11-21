# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Minimal exploration subflow for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_exploration_workflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Run one generic Explorer stage for a dispatched work item."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_explorer_work",
        "acquire_explorer",
        "exploration_chat",
        "wait_for_stage_completion",
        "exploration_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_edge(START, "dispatch_explorer_work")
    graph.add_edge("dispatch_explorer_work", "acquire_explorer")
    graph.add_edge("acquire_explorer", "exploration_chat")
    graph.add_edge("exploration_chat", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "exploration_area_complete")
    graph.add_edge("exploration_area_complete", END)
    return graph
