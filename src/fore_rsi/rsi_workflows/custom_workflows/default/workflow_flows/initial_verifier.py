# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Initial Verifier setup for the default workflow."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from ..agents.verifier import VerifierAgent

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_initial_verifier_workflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Create the initial Verifier and initialize general verification context."""
    graph = StateGraph(dict)
    graph.add_node(
        "create_initial_verifier",
        partial(
            workflow.request_agent_creation,
            agent_class=VerifierAgent,
            agent_config=workflow.default_agent_config,
        ),
    )
    for node_name in ("verifier_pool_chat", "verifier_pool_ready"):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_edge(START, "create_initial_verifier")
    graph.add_edge("create_initial_verifier", "verifier_pool_chat")
    graph.add_edge("verifier_pool_chat", "verifier_pool_ready")
    graph.add_edge("verifier_pool_ready", END)
    return graph
