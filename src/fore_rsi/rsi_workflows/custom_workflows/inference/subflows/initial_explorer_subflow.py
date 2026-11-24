# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Initial Explorer bootstrap for inference optimization."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from fore_rsi.rsi_workflows.custom_workflows.default.agents.explorer import ExplorerAgent

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_initial_explorer_subflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Build the inference baseline subflow before filling Explorer slots."""
    graph = StateGraph(dict)
    for node_name in (
        "define_initial_baseline",
        "define_baseline_experiment",
        "register_baseline_candidate",
        "fill_explorer_slots",
        "exploration_bootstrap_ready",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node(
        "create_initial_explorer",
        partial(
            workflow.request_agent_creation,
            agent_class=ExplorerAgent,
            agent_config=workflow.default_agent_config,
        ),
    )
    graph.add_node("study_framework", lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    graph.add_edge(START, "create_initial_explorer")
    graph.add_edge("create_initial_explorer", "study_framework")
    graph.add_edge("study_framework", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "explorer_stage_route", "define_initial_baseline"
        ),
        {
            "define_initial_baseline": "define_initial_baseline",
            "define_baseline_experiment": "define_baseline_experiment",
            "register_baseline_candidate": "register_baseline_candidate",
            "fill_explorer_slots": "fill_explorer_slots",
            "exploration_bootstrap_ready": "exploration_bootstrap_ready",
        },
    )
    graph.add_edge("define_initial_baseline", "wait_for_stage_completion")
    graph.add_edge("define_baseline_experiment", "wait_for_stage_completion")
    graph.add_edge("register_baseline_candidate", "fill_explorer_slots")
    graph.add_edge("fill_explorer_slots", "exploration_bootstrap_ready")
    graph.add_edge("exploration_bootstrap_ready", END)
    return graph
