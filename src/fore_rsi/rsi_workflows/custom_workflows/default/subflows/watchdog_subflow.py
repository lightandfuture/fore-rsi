# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow Watchdog timer, observation, and feedback subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_watchdog_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the periodic Watchdog subflow for workflow-wide progress checks.

    START --> create_watchdog
                  -> wait_for_watchdog_timer
                  --> collect_agent_sessions
                  --> collect_task_artifacts
                  --> review_workflow (MCP: inspect sessions and artifacts, submit review)
                  --> wait_for_settle_and_tool_subflow[A=watchdog_action,B=review_workflow,C=END]
    watchdog_action --> send_reminders --> publish_watchdog_report
    --> publish_watchdog_knowledge --> wait_for_watchdog_timer
    """
    return StateGraph(dict)
