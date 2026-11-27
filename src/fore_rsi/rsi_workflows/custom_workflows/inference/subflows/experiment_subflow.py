# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Inference experiment admission, execution, and feedback subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_experiment_subflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Build the inference subflow that allocates an Experimenter, runs an experiment, and evaluates its result."""
    graph = StateGraph(dict)
    for node_name in (
        "dispatch_experiment_work",
        "wait_for_experimenter_slot",
        "acquire_experimenter",
        "prepare_experiment",
        "wait_for_experiment_resources",
        "run_experiment",
        "evaluate_experiment_result",
        "record_experiment_result",
        "publish_report",
        "publish_feedback",
        "release_experimenter_slot",
        "route_experiment_decision",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    # START -> dispatch_experiment_work -> wait_for_experimenter_slot
    #          -> acquire_experimenter -> prepare_experiment
    #          -> wait_for_experiment_resources -> run_experiment
    #          -> wait_for_stage_completion -> evaluate_experiment_result
    #          -> wait_for_stage_completion -> route_experiment_decision
    #              +--------------+------------------+
    #              |                    |                  |
    #          retry_experiment record_experiment_result publish_feedback
    #              |                    |                  |
    #       prepare_experiment     publish_report       release_experimenter_slot
    #                                      |             |
    #                                publish_report     |
    #                                      +------+------+
    #                                             |
    #                                release_experimenter_slot -> END
    graph.add_edge(START, "dispatch_experiment_work")
    graph.add_edge("dispatch_experiment_work", "wait_for_experimenter_slot")
    graph.add_edge("wait_for_experimenter_slot", "acquire_experimenter")
    graph.add_edge("acquire_experimenter", "prepare_experiment")
    graph.add_edge("prepare_experiment", "wait_for_experiment_resources")
    graph.add_edge("wait_for_experiment_resources", "run_experiment")
    graph.add_edge("run_experiment", "wait_for_stage_completion")
    graph.add_edge("evaluate_experiment_result", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "experiment_stage_route", "evaluate_experiment_result"
        ),
        {
            "evaluate_experiment_result": "evaluate_experiment_result",
            "route_experiment_decision": "route_experiment_decision",
        },
    )
    graph.add_conditional_edges(
        "route_experiment_decision",
        lambda workflow_state: workflow_state.get(
            "experiment_decision", "publish_experiment_result"
        ),
        {
            "publish_experiment_result": "record_experiment_result",
            "retry_experiment": "prepare_experiment",
            "return_feedback": "publish_feedback",
        },
    )
    graph.add_edge("record_experiment_result", "publish_report")
    graph.add_edge("publish_report", "release_experimenter_slot")
    graph.add_edge("publish_feedback", "release_experimenter_slot")
    graph.add_edge("release_experimenter_slot", END)
    return graph
