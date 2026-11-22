# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Initial Verifier bootstrap for inference optimization."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from fore_rsi.rsi_workflows.custom_workflows.default.agents.verifier import VerifierAgent

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_initial_verifier_subflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Build the inference Verifier bootstrap subflow without blocking exploration."""
    graph = StateGraph(dict)
    for node_name in (
        "prepare_verifier_resources",
        "fill_verifier_slots",
        "confirm_verifier_context",
        "verifier_pool_ready",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node(
        "create_initial_verifier",
        partial(
            workflow.request_agent_creation,
            agent_class=VerifierAgent,
            agent_config=workflow.default_agent_config,
        ),
    )
    graph.add_node("study_verifier_context", lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    graph.add_edge(START, "create_initial_verifier")
    graph.add_edge("create_initial_verifier", "study_verifier_context")
    graph.add_edge("study_verifier_context", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "verifier_stage_route", "prepare_verifier_resources"
        ),
        {
            "prepare_verifier_resources": "prepare_verifier_resources",
            "fill_verifier_slots": "fill_verifier_slots",
            "verifier_pool_ready": "verifier_pool_ready",
        },
    )
    graph.add_edge("prepare_verifier_resources", "wait_for_stage_completion")
    graph.add_edge("fill_verifier_slots", "confirm_verifier_context")
    graph.add_edge("confirm_verifier_context", "verifier_pool_ready")
    graph.add_edge("verifier_pool_ready", END)
    return graph
