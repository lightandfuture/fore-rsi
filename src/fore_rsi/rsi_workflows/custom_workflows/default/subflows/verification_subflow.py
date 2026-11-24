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
        "route_verification_stage",
        "create_verifier_workgroup",
        "study_verification_criteria",
        "fork_verifier",
        "wait_verifier_resource_quota",
        "select_verifier_resources",
        "check_verifier_resource_assignment",
        "revise_verifier_resource_assignment",
        "commit_verifier_resource_assignment",
        "verification",
        "queue_exploration_feedback",
        "publish_verification_result",
    ):
        graph.add_node(node_name, lambda workflow_state: {})

    # START --> route_verification_stage
    #             +--[initialize_verifier] --> create_verifier_workgroup
    #             |                            -> study_verification_criteria
    #             |                            -> fork_verifier
    #             |                            -> route_verification_stage
    #             |
    #             +--[select_resources] ------> wait_verifier_resource_quota
    #             |                            -> select_verifier_resources
    #             |                            -> route_verification_stage
    #             +--[checking_resources] ----> check_verifier_resource_assignment
    #             |                            -> route_verification_stage
    #             +--[resource_rejected] -----> revise_verifier_resource_assignment
    #             |                            -> route_verification_stage
    #             +--[resource_confirmed] ----> commit_verifier_resource_assignment
    #             |                            -> route_verification_stage
    #             +--[verification] ----------> verification
    #             |                            -> route_verification_stage
    #             +--[revise_exploration] ---> queue_exploration_feedback
    #             |                            -> END
    #             +--[verification_complete]-> publish_verification_result
    #                                          -> END
    graph.add_edge(START, "route_verification_stage")
    graph.add_conditional_edges(
        "route_verification_stage",
        lambda workflow_state: workflow_state.get(
            "next_verification_stage",
            (
                "initialize_verifier"
                if workflow_state.get("is_first_task_submission", False)
                and not workflow_state.get("verifier_context_ready", False)
                else "verification"
            ),
        ),
        {
            "initialize_verifier": "create_verifier_workgroup",
            "select_resources": "wait_verifier_resource_quota",
            "checking_resources": "check_verifier_resource_assignment",
            "resource_rejected": "revise_verifier_resource_assignment",
            "resource_confirmed": "commit_verifier_resource_assignment",
            "verification": "verification",
            "revise_exploration": "queue_exploration_feedback",
            "verification_complete": "publish_verification_result",
        },
    )
    graph.add_edge("create_verifier_workgroup", "study_verification_criteria")
    graph.add_edge("study_verification_criteria", "fork_verifier")
    graph.add_edge("fork_verifier", "route_verification_stage")
    graph.add_edge("wait_verifier_resource_quota", "select_verifier_resources")
    graph.add_edge("select_verifier_resources", "route_verification_stage")
    graph.add_edge("check_verifier_resource_assignment", "route_verification_stage")
    graph.add_edge("revise_verifier_resource_assignment", "route_verification_stage")
    graph.add_edge("commit_verifier_resource_assignment", "route_verification_stage")
    graph.add_edge("verification", "route_verification_stage")
    graph.add_edge("queue_exploration_feedback", END)
    graph.add_edge("publish_verification_result", END)
    return graph
