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
                --> wait_for_settle[A=watchdog_action,B=review_workflow]

    watchdog_action
        +--[send_reminders]    --> send_reminders --> END
        +--[publish_report]    --> publish_watchdog_report --> END
        +--[publish_knowledge] --> publish_watchdog_knowledge --> END
        +--[continue_watchdog] --> wait_for_watchdog_timer
    """
    return StateGraph(dict)
