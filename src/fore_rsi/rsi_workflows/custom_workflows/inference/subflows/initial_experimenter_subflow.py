# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Initial Experimenter bootstrap for inference optimization."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from fore_rsi.rsi_workflows.custom_workflows.default.agents.experimenter import ExperimenterAgent

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_initial_experimenter_subflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Build the inference Experimenter bootstrap subflow without blocking exploration."""
    graph = StateGraph(dict)
    for node_name in (
        "prepare_experimenter_resources",
        "fill_experimenter_slots",
        "confirm_experimenter_context",
        "experimenter_pool_ready",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node(
        "create_initial_experimenter",
        partial(
            workflow.request_agent_creation,
            agent_class=ExperimenterAgent,
            agent_config=workflow.default_agent_config,
        ),
    )
    graph.add_node("study_experimenter_context", lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    graph.add_edge(START, "create_initial_experimenter")
    graph.add_edge("create_initial_experimenter", "study_experimenter_context")
    graph.add_edge("study_experimenter_context", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "experimenter_stage_route", "prepare_experimenter_resources"
        ),
        {
            "prepare_experimenter_resources": "prepare_experimenter_resources",
            "fill_experimenter_slots": "fill_experimenter_slots",
            "experimenter_pool_ready": "experimenter_pool_ready",
        },
    )
    graph.add_edge("prepare_experimenter_resources", "wait_for_stage_completion")
    graph.add_edge("fill_experimenter_slots", "confirm_experimenter_context")
    graph.add_edge("confirm_experimenter_context", "experimenter_pool_ready")
    graph.add_edge("experimenter_pool_ready", END)
    return graph
