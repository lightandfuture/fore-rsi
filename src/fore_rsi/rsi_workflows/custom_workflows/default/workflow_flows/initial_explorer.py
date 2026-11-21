# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Initial Explorer setup for the default workflow."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from ..agents.explorer import ExplorerAgent

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_initial_explorer_workflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Create the initial Explorer and run one general context conversation."""
    graph = StateGraph(dict)
    graph.add_node(
        "create_initial_explorer",
        partial(
            workflow.request_agent_creation,
            agent_class=ExplorerAgent,
            agent_config=workflow.default_agent_config,
        ),
    )
    for node_name in ("initial_explorer_chat", "initial_explorer_ready"):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_edge(START, "create_initial_explorer")
    graph.add_edge("create_initial_explorer", "initial_explorer_chat")
    graph.add_edge("initial_explorer_chat", "initial_explorer_ready")
    graph.add_edge("initial_explorer_ready", END)
    return graph
