# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Verifier setup and verification subflow for the default workflow."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from ..agents.verifier import VerifierAgent

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_verification_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the Verifier setup and verification subflow for the default workflow."""
    graph = StateGraph(dict)
    graph.add_node(
        "create_initial_verifier",
        partial(
            workflow.request_agent_creation,
            agent_class=VerifierAgent,
            agent_config=workflow.default_agent_config,
        ),
    )
    for node_name in (
        "verifier_pool_chat",
        "verifier_pool_ready",
        "dispatch_verification_work",
        "wait_for_verifier_slot",
        "acquire_verifier",
        "verifier_chat",
        "wait_for_stage_completion",
        "verification_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})

    # Prepare the shared Verifier context before accepting verification work.
    graph.add_edge(START, "create_initial_verifier")
    graph.add_edge("create_initial_verifier", "verifier_pool_chat")
    graph.add_edge("verifier_pool_chat", "verifier_pool_ready")
    graph.add_edge("verifier_pool_ready", "dispatch_verification_work")
    graph.add_edge("dispatch_verification_work", "wait_for_verifier_slot")
    graph.add_edge("wait_for_verifier_slot", "acquire_verifier")
    graph.add_edge("acquire_verifier", "verifier_chat")
    graph.add_edge("verifier_chat", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "verification_area_complete")
    graph.add_edge("verification_area_complete", END)
    return graph
