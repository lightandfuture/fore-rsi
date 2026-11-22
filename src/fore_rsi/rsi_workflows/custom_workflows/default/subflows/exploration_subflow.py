# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Minimal exploration subflow for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_exploration_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build one generic Explorer subflow for the current task."""
    graph = StateGraph(dict)
    for node_name in (
        "route_exploration_stage",
        "initialize_explorer_context",
        "acquire_explorer",
        "exploration_chat",
        "wait_for_stage_completion",
        "exploration_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})

    # START -> route_exploration_stage
    #             +--[initialize_explorer]--> initialize_explorer_context --+
    #             |                                                        |
    #             +--[existing_task]----------------------------------------+
    #                                                                          |
    #                                                                          v
    #                                                                  acquire_explorer
    #                                                                          |
    #                                                                          v
    #                                                                  exploration_chat
    #                                                                          |
    #                                                                          v
    #                                                              wait_for_stage_completion
    #                                                                          |
    #                                                                          v
    #                                                              exploration_area_complete
    #                                                                          |
    #                                                                          v
    #                                                                         END
    graph.add_edge(START, "route_exploration_stage")
    graph.add_conditional_edges(
        "route_exploration_stage",
        lambda workflow_state: (
            "initialize_explorer"
            if workflow_state.get("is_first_task_submission", False)
            else "existing_task"
        ),
        {
            "initialize_explorer": "initialize_explorer_context",
            "existing_task": "acquire_explorer",
        },
    )
    graph.add_edge("initialize_explorer_context", "acquire_explorer")
    graph.add_edge("acquire_explorer", "exploration_chat")
    graph.add_edge("exploration_chat", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "exploration_area_complete")
    graph.add_edge("exploration_area_complete", END)
    return graph
