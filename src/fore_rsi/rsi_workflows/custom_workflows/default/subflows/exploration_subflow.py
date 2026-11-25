# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Explorer research, implementation, feedback, and Workgroup lifecycle subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_exploration_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the Explorer subflow for direction selection, implementation, and handoff.

    START --> route_exploration_stage
                +--[initialize_explorer] --> create_workgroup (explorer + checker)
                |                            --> study_framework
                |                            --> fork_explorer [quota = 4]
                |                                 +--[explorer_i]
                |                                        --> route_exploration_stage[select_direction]
                +--[select_direction] ------> wait_direction_quota
                |                            --> exploration_direction (MCP)
                |                            --> wait_for_settle_and_tool_subflow[A=checking_direction,B=exploration_direction,C=retire]
                +--[checking_direction] ----> check_exploration_direction (MCP)
                |                            --> wait_for_settle_and_tool_subflow[A=direction_check_result,B=check_exploration_direction,C=retire]
                +--[exploration] ----------> [check_exploration_switch]
                |                                 --> exploration (MCP, including update_direction_pool)
                |                                 --> wait_for_settle_and_tool_subflow[A=checking,B=exploration,C=retire]
                +--[checking] --------------> check_exploration (MCP)
                |                            --> wait_for_settle_and_tool_subflow[A=route_exploration_stage[exploration/submit_to_verification/retire],B=check_exploration,C=retire]
                +--[switch_exploration] ---> [check_exploration_switch]
                                              +--[preempt]
                                              |      --> wait_for_preempt
                                              |      --> route_exploration_stage[exploration]
                                              +--[create_explorer]
                                              |      --> create_workgroup
                                              |      --> fork_explorer
                                              |      --> route_exploration_stage[select_direction]
                                              +--[wake_explorer]
                                              |      --> wake_explorer
                                              +--[release_explorer_slot]
                                                     --> release_explorer_slot
                                                     --> route_exploration_stage[wake_explorer/create_explorer]
                +--[submit_to_verification] --> update_direction_pool
                                              --> update_code_pool --> END[verification]

    direction_check_result
        +--[direction_confirmed] --> update_direction_pool --> route_exploration_stage[exploration]
        +--[direction_rejected]  --> exploration_direction
        +--[exceed_limit_try]    --> retire

    retire --> retire_workgroup --> END[finish]
    """
    return StateGraph(dict)
