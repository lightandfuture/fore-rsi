# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Inference Worker implementation and Candidate handoff subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_work_subflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Build one inference Worker subflow from Proposal to Candidate handoff."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_worker_work",
        "acquire_worker",
        "receive_proposal",
        "implement_candidate",
        "create_checker",
        "check_implementation",
        "publish_candidate",
        "queue_experiment_request",
        "return_to_explorer",
        "release_worker_slot",
        "route_implementation_decision",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    # START -> dispatch_worker_work -> acquire_worker -> receive_proposal
    #          -> implement_candidate -> wait_for_stage_completion
    #          -> create_checker -> check_implementation
    #          -> wait_for_stage_completion -> route_implementation_decision
    #              +-------------------+-------------------+----------------+
    #              |                   |                   |
    #          revise_implementation publish_candidate return_to_explorer
    #              |                   |                   |
    #       implement_candidate queue_experiment_request release_worker_slot
    #                                  |                   |
    #                          release_worker_slot -> END
    graph.add_edge(START, "dispatch_worker_work")
    graph.add_edge("dispatch_worker_work", "acquire_worker")
    graph.add_edge("acquire_worker", "receive_proposal")
    graph.add_edge("receive_proposal", "implement_candidate")
    graph.add_edge("implement_candidate", "wait_for_stage_completion")
    graph.add_edge("create_checker", "check_implementation")
    graph.add_edge("check_implementation", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "implementation_stage_route", "create_checker"
        ),
        {
            "create_checker": "create_checker",
            "check_implementation": "check_implementation",
            "route_implementation_decision": "route_implementation_decision",
        },
    )
    graph.add_conditional_edges(
        "route_implementation_decision",
        lambda workflow_state: workflow_state.get(
            "implementation_decision", "publish_candidate"
        ),
        {
            "publish_candidate": "publish_candidate",
            "revise_implementation": "implement_candidate",
            "request_experiment": "queue_experiment_request",
            "return_to_explorer": "return_to_explorer",
        },
    )
    graph.add_edge("publish_candidate", "queue_experiment_request")
    graph.add_edge("queue_experiment_request", "release_worker_slot")
    graph.add_edge("return_to_explorer", "release_worker_slot")
    graph.add_edge("release_worker_slot", END)
    return graph
