# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Inference experiment admission, execution, and feedback subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_experiment_subflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Build one inference experiment subflow through Verifier admission and evaluation."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_experiment_work",
        "wait_for_verifier_slot",
        "acquire_verifier",
        "prepare_experiment",
        "wait_for_experiment_resources",
        "run_experiment",
        "verify_result",
        "record_experiment_result",
        "publish_report",
        "publish_feedback",
        "release_verifier_slot",
        "route_verification_decision",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    # START -> dispatch_experiment_work -> wait_for_verifier_slot
    #          -> acquire_verifier -> prepare_experiment
    #          -> wait_for_experiment_resources -> run_experiment
    #          -> wait_for_stage_completion -> verify_result
    #          -> wait_for_stage_completion -> route_verification_decision
    #              +--------------+------------------+
    #              |                    |                  |
    #          retry_experiment record_experiment_result publish_feedback
    #              |                    |                  |
    #       prepare_experiment     publish_report       release_verifier_slot
    #                                      |             |
    #                                publish_report     |
    #                                      +------+------+
    #                                             |
    #                                release_verifier_slot -> END
    graph.add_edge(START, "dispatch_experiment_work")
    graph.add_edge("dispatch_experiment_work", "wait_for_verifier_slot")
    graph.add_edge("wait_for_verifier_slot", "acquire_verifier")
    graph.add_edge("acquire_verifier", "prepare_experiment")
    graph.add_edge("prepare_experiment", "wait_for_experiment_resources")
    graph.add_edge("wait_for_experiment_resources", "run_experiment")
    graph.add_edge("run_experiment", "wait_for_stage_completion")
    graph.add_edge("verify_result", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "experiment_stage_route", "verify_result"
        ),
        {
            "verify_result": "verify_result",
            "route_verification_decision": "route_verification_decision",
        },
    )
    graph.add_conditional_edges(
        "route_verification_decision",
        lambda workflow_state: workflow_state.get(
            "verification_decision", "publish_experiment_result"
        ),
        {
            "publish_experiment_result": "record_experiment_result",
            "retry_experiment": "prepare_experiment",
            "return_feedback": "publish_feedback",
        },
    )
    graph.add_edge("record_experiment_result", "publish_report")
    graph.add_edge("publish_report", "release_verifier_slot")
    graph.add_edge("publish_feedback", "release_verifier_slot")
    graph.add_edge("release_verifier_slot", END)
    return graph
