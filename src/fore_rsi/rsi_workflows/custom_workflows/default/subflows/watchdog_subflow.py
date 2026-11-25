# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow Watchdog timer, observation, and feedback subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from .agent_turn import wait_for_settle

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_watchdog_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the periodic Watchdog subflow for workflow-wide progress checks.

    START --> create_watchdog
                -> wait_for_watchdog_timer
                --> collect_agent_sessions
                --> collect_task_artifacts
                --> review_workflow (MCP: inspect sessions and artifacts, submit review)
                --> wait_for_settle[A=watchdog_action,B=review_workflow]

    watchdog_action
        +--[send_reminders]    --> send_reminders --> END
        +--[publish_report]    --> publish_watchdog_report --> END
        +--[publish_knowledge] --> publish_watchdog_knowledge --> END
        +--[continue_watchdog] --> wait_for_watchdog_timer
    """
    graph = StateGraph(dict)
    for node_name in (
        "route_watchdog_stage",
        "create_watchdog",
        "wait_for_watchdog_timer",
        "collect_agent_sessions",
        "collect_task_artifacts",
        "review_workflow",
        "is_tool_submission",
        "exceed_limit_try",
        "watchdog_action",
        "send_reminders",
        "publish_watchdog_report",
        "publish_watchdog_knowledge",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_settle", wait_for_settle)

    graph.add_edge(START, "route_watchdog_stage")
    graph.add_conditional_edges(
        "route_watchdog_stage",
        lambda workflow_state: workflow_state.get(
            "next_watchdog_stage",
            (
                "initialize_watchdog"
                if not workflow_state.get("watchdog_context_ready", False)
                else "watchdog_round"
            ),
        ),
        {
            "initialize_watchdog": "create_watchdog",
            "watchdog_round": "wait_for_watchdog_timer",
        },
    )
    graph.add_edge("create_watchdog", "wait_for_watchdog_timer")
    graph.add_edge("wait_for_watchdog_timer", "collect_agent_sessions")
    graph.add_edge("collect_agent_sessions", "collect_task_artifacts")
    graph.add_edge("collect_task_artifacts", "review_workflow")
    graph.add_edge("review_workflow", "wait_for_settle")
    graph.add_edge("wait_for_settle", "is_tool_submission")
    graph.add_conditional_edges(
        "is_tool_submission",
        lambda workflow_state: workflow_state.get(
            "next_watchdog_submission_stage", "exceed_limit_try"
        ),
        {
            "watchdog_action": "watchdog_action",
            "review_workflow": "review_workflow",
            "exceed_limit_try": "exceed_limit_try",
        },
    )
    graph.add_conditional_edges(
        "watchdog_action",
        lambda workflow_state: workflow_state.get(
            "watchdog_action", "continue_watchdog"
        ),
        {
            "send_reminders": "send_reminders",
            "publish_report": "publish_watchdog_report",
            "publish_knowledge": "publish_watchdog_knowledge",
            "continue_watchdog": "wait_for_watchdog_timer",
        },
    )
    graph.add_edge("send_reminders", END)
    graph.add_edge("publish_watchdog_report", END)
    graph.add_edge("publish_watchdog_knowledge", END)
    graph.add_edge("exceed_limit_try", END)
    return graph
