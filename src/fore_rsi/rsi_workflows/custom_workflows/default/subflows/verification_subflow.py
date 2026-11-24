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
        "lock_select_resources",
        "select_verifier_resources",
        "unlock_select_resources",
        "select_verifier",
        "verification",
        "wait_for_settle",
        "is_tool_submission",
        "exceed_limit_try",
        "publish_result",
        "queue_exploration_feedback",
    ):
        graph.add_node(node_name, lambda workflow_state: {})

    # START --> route_verification_stage
    #             +--[initialize_verifier] --> create_verifier_workgroup
    #             |                            --> study_verification_criteria
    #             |                            --> fork_verifier [seed = study_verification_criteria, quota = 2]
    #             |                                 +--[verifier_1] --> route_verification_stage[select_resources]
    #             |                                 +--[verifier_2] --> route_verification_stage[select_resources]
    #             +--[select_resources] ------> lock_select_resources
    #             |                            --> select_verifier_resources
    #             |                            --> wait_for_settle --> is_tool_submission
    #             |                                +--[is_tool_submission]
    #             |                                |      --> unlock_select_resources --> END
    #             |                                +--[not_tool_submission]
    #             |                                |      --> select_verifier_resources
    #             |                                +--[exceed_limit_try]
    #             |                                       --> END
    #             +--[verification] ----------> select_verifier --> verification (experimenting)
    #             |                            --> wait_for_settle --> is_tool_submission
    #             |                                +--[is_tool_submission]
    #             |                                |      --> publish_result --> queue_exploration_feedback --> END[exploration]
    #             |                                +--[not_tool_submission]
    #             |                                |      --> verification
    #             |                                +--[exceed_limit_try]
    #             |                                       --> END
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
            "select_resources": "lock_select_resources",
            "verification": "select_verifier",
            "revise_exploration": "queue_exploration_feedback",
            "verification_complete": "publish_result",
        },
    )
    graph.add_edge("create_verifier_workgroup", "study_verification_criteria")
    graph.add_edge("study_verification_criteria", "fork_verifier")
    graph.add_edge("fork_verifier", "route_verification_stage")
    graph.add_edge("lock_select_resources", "select_verifier_resources")
    graph.add_edge("select_verifier_resources", "wait_for_settle")
    graph.add_edge("select_verifier", "verification")
    graph.add_edge("verification", "wait_for_settle")
    graph.add_edge("wait_for_settle", "is_tool_submission")
    graph.add_conditional_edges(
        "is_tool_submission",
        lambda workflow_state: workflow_state.get(
            "next_verification_submission_stage", "exceed_limit_try"
        ),
        {
            "unlock_select_resources": "unlock_select_resources",
            "select_verifier_resources": "select_verifier_resources",
            "publish_result": "publish_result",
            "verification": "verification",
            "exceed_limit_try": "exceed_limit_try",
        },
    )
    graph.add_edge("unlock_select_resources", END)
    graph.add_edge("exceed_limit_try", END)
    graph.add_edge("publish_result", "queue_exploration_feedback")
    graph.add_edge("queue_exploration_feedback", END)
    return graph
