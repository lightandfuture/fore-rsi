# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Minimal Verifier subflow for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_experiment_workflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Run one generic Verifier stage for an accepted experiment request."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_experiment_work",
        "wait_for_verifier_slot",
        "acquire_verifier",
        "verifier_chat",
        "wait_for_stage_completion",
        "experiment_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_edge(START, "dispatch_experiment_work")
    graph.add_edge("dispatch_experiment_work", "wait_for_verifier_slot")
    graph.add_edge("wait_for_verifier_slot", "acquire_verifier")
    graph.add_edge("acquire_verifier", "verifier_chat")
    graph.add_edge("verifier_chat", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "experiment_area_complete")
    graph.add_edge("experiment_area_complete", END)
    return graph
