# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Explorer research, implementation, feedback, and Workgroup lifecycle subflow."""

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import StateGraph

from ..agents.checker import CheckerAgent
from ..agents.explorer import ExplorerAgent

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
                |                            --> wait_for_settle[A=checking_direction,B=exploration_direction]
                +--[checking_direction] ----> check_exploration_direction (MCP)
                |                            --> wait_for_settle[A=route_exploration_stage[direction_confirmed/direction_rejected/exceed_limit_try],B=check_exploration_direction]
                +--[direction_confirmed] --> update_direction_pool
                |                            --> route_exploration_stage[exploration]
                +--[direction_rejected] --> exploration_direction
                +--[exploration] ----------> [check_exploration_switch]
                |                                 --> exploration (MCP, including update_direction_pool)
                |                                 --> wait_for_settle[A=checking,B=exploration]
                +--[checking] --------------> check_exploration (MCP)
                |                            --> wait_for_settle[A=route_exploration_stage[exploration/submit_to_verification/retire],B=check_exploration]
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

    retire --> retire_workgroup --> END[finish]
    """
    graph = StateGraph(dict)
    graph.add_node(
        "create_workgroup",
        partial(
            workflow.create_workgroup,
            agents=[
                (ExplorerAgent, workflow.default_agent_config),
                (CheckerAgent, workflow.default_agent_config),
            ],
        ),
    )
    return graph
