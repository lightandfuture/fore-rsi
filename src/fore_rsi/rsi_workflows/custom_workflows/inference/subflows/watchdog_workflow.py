# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Inference Watchdog review and feedback subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import InferenceWorkflow


def build_watchdog_workflow(workflow: "InferenceWorkflow") -> StateGraph:
    """Run periodic Watchdog review and feedback for inference work items."""
    graph = StateGraph(dict)
    for node_name in (
        "create_watchdog",
        "collect_progress",
        "review_progress",
        "send_reminders",
        "publish_watchdog_report",
        "route_watchdog_decision",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_stage_completion", lambda workflow_state: {})
    graph.add_node("route_stage_completion", lambda workflow_state: {})

    # START -> create_watchdog -> collect_progress -> review_progress
    #                                      |
    #                              wait_for_stage_completion
    #                                      |
    #                              route_watchdog_decision
    #                         +------------+-------------+
    #                         |                          |
    #                  continue_watchdog            send_reminders
    #                         |                          |
    #                  collect_progress             collect_progress
    #
    # publish_watchdog_report -> END.
    graph.add_edge(START, "create_watchdog")
    graph.add_edge("create_watchdog", "collect_progress")
    graph.add_edge("collect_progress", "review_progress")
    graph.add_edge("review_progress", "wait_for_stage_completion")
    graph.add_edge("wait_for_stage_completion", "route_stage_completion")
    graph.add_conditional_edges(
        "route_stage_completion",
        lambda workflow_state: workflow_state.get(
            "watchdog_stage_route", "route_watchdog_decision"
        ),
        {"route_watchdog_decision": "route_watchdog_decision"},
    )
    graph.add_conditional_edges(
        "route_watchdog_decision",
        lambda workflow_state: workflow_state.get(
            "watchdog_decision", "publish_watchdog_report"
        ),
        {
            "publish_watchdog_report": "publish_watchdog_report",
            "send_reminders": "send_reminders",
            "continue_watchdog": "collect_progress",
        },
    )
    graph.add_edge("send_reminders", "collect_progress")
    graph.add_edge("publish_watchdog_report", END)
    return graph
