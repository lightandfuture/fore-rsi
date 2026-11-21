# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Minimal Worker subflow for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_work_workflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Run one generic Worker stage for an accepted work item."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_worker_work",
        "acquire_worker",
        "worker_chat",
        "wait_for_stage_completion",
        "work_area_complete",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_edge(START, "dispatch_worker_work")
    graph.add_edge("dispatch_worker_work", "acquire_worker")
    graph.add_edge("acquire_worker", "worker_chat")
    graph.add_edge("worker_chat", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "work_area_complete")
    graph.add_edge("work_area_complete", END)
    return graph
