# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Inference Explorer exploration and Proposal handoff subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_exploration_workflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Run one inference Explorer work item from direction discovery to handoff."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_explorer_work",
        "acquire_explorer",
        "explore_direction",
        "create_checker",
        "check_exploration",
        "create_proposal",
        "check_proposal",
        "publish_proposal",
        "queue_worker_request",
        "queue_experiment_request",
        "suspend_explorer",
        "release_explorer_slot",
        "retire_explorer",
        "finish_exploration",
        "route_exploration_decision",
        "route_proposal_decision",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    # START -> dispatch_explorer_work -> acquire_explorer -> explore_direction
    #                                                        |
    #                                                wait_for_stage_completion
    #                                                        |
    #                                                create_checker -> check_exploration
    #                                                        |
    #                                                wait_for_stage_completion
    #                                                        |
    #                                             route_exploration_decision
    #                                         +----------+------------+
    #                                         |                       |
    #                                  continue_exploration     create_proposal
    #                                         |                       |
    #                                  explore_direction       check_proposal
    #                                                                    |
    #                                                           route_proposal_decision
    #                                                     +---------+---------+---------+
    #                                                     |                   |         |
    #                                                  revise_exploration   publish_proposal   request_experiment
    #                                                     |                       |                 |
    #                                              explore_direction    queue_worker_request  queue_experiment_request
    #                                                                           \       /
    #                                                                      release_explorer_slot
    #                                                                                |
    #                                                                         suspend_explorer -> END
    graph.add_edge(START, "dispatch_explorer_work")
    graph.add_edge("dispatch_explorer_work", "acquire_explorer")
    graph.add_edge("acquire_explorer", "explore_direction")
    graph.add_edge("explore_direction", "wait_for_stage_completion")
    graph.add_edge("create_checker", "check_exploration")
    graph.add_edge("check_exploration", "wait_for_stage_completion")
    graph.add_edge("create_proposal", "wait_for_stage_completion")
    graph.add_edge("check_proposal", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "exploration_stage_route", "create_checker"
        ),
        {
            "create_checker": "create_checker",
            "check_exploration": "check_exploration",
            "route_exploration_decision": "route_exploration_decision",
            "create_proposal": "create_proposal",
            "check_proposal": "check_proposal",
            "route_proposal_decision": "route_proposal_decision",
        },
    )
    graph.add_conditional_edges(
        "route_exploration_decision",
        lambda workflow_state: workflow_state.get(
            "exploration_decision", "create_proposal"
        ),
        {
            "create_proposal": "create_proposal",
            "continue_exploration": "explore_direction",
            "finish_exploration": "finish_exploration",
        },
    )
    graph.add_conditional_edges(
        "route_proposal_decision",
        lambda workflow_state: workflow_state.get(
            "proposal_decision", "publish_proposal"
        ),
        {
            "publish_proposal": "publish_proposal",
            "revise_exploration": "explore_direction",
            "request_experiment": "queue_experiment_request",
        },
    )
    graph.add_edge("publish_proposal", "queue_worker_request")
    graph.add_edge("queue_worker_request", "release_explorer_slot")
    graph.add_edge("queue_experiment_request", "release_explorer_slot")
    graph.add_edge("release_explorer_slot", "suspend_explorer")
    graph.add_edge("suspend_explorer", END)
    graph.add_edge("finish_exploration", "retire_explorer")
    graph.add_edge("retire_explorer", END)
    return graph
