# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Verifier subflow graph for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_verification_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the Verifier subflow graph for the default workflow."""
    graph = StateGraph(dict)
    for node_name in (
        "create_initial_verifier",
        "verifier_pool_chat",
        "verifier_pool_ready",
        "dispatch_verification_work",
        "wait_for_verifier_slot",
        "acquire_verifier",
        "verifier_chat",
        "verification_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})

    # START -> create_initial_verifier -> verifier_pool_chat
    #          -> verifier_pool_ready -> dispatch_verification_work
    #          -> wait_for_verifier_slot -> acquire_verifier
    #          -> verifier_chat -> verification_area_complete -> END
    graph.add_edge(START, "create_initial_verifier")
    graph.add_edge("create_initial_verifier", "verifier_pool_chat")
    graph.add_edge("verifier_pool_chat", "verifier_pool_ready")
    graph.add_edge("verifier_pool_ready", "dispatch_verification_work")
    graph.add_edge("dispatch_verification_work", "wait_for_verifier_slot")
    graph.add_edge("wait_for_verifier_slot", "acquire_verifier")
    graph.add_edge("acquire_verifier", "verifier_chat")
    graph.add_edge("verifier_chat", "verification_area_complete")
    graph.add_edge("verification_area_complete", END)
    return graph
