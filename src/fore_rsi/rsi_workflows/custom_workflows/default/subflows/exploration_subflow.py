# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Explorer research, implementation, feedback, and Workgroup lifecycle subflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from .agent_turn import wait_for_settle

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
    for node_name in (
        "route_exploration_stage",
        "create_workgroup",
        "study_framework",
        "fork_explorer",
        "wait_direction_quota",
        "exploration_direction",
        "check_exploration_direction",
        "add_to_exploration_direction_pool",
        "revise_exploration_direction",
        "check_exploration_switch",
        "preempt_explorer",
        "wait_for_explorer_attempt_end",
        "wake_explorer",
        "exploration",
        "check_exploration",
        "update_exploration_direction",
        "update_exploration_direction_pool",
        "add_to_exploration_code_pool",
        "queue_verification_request",
        "release_explorer_slot",
        "retire_workgroup",
        "is_tool_submission",
        "exceed_limit_try",
        "exceed_explore_try",
    ):
        graph.add_node(node_name, lambda workflow_state: {})
    graph.add_node("wait_for_settle", wait_for_settle)

    graph.add_edge(START, "route_exploration_stage")
    graph.add_conditional_edges(
        "route_exploration_stage",
        lambda workflow_state: workflow_state.get(
            "next_exploration_stage",
            (
                "initialize_explorer"
                if workflow_state.get("is_first_task_submission", False)
                and not workflow_state.get("explorer_context_ready", False)
                else "exploration"
            ),
        ),
        {
            "initialize_explorer": "create_workgroup",
            "select_direction": "wait_direction_quota",
            "checking_direction": "check_exploration_direction",
            "direction_rejected": "revise_exploration_direction",
            "direction_confirmed": "add_to_exploration_direction_pool",
            "improvement_confirmed": "update_exploration_direction_pool",
            "switch_exploration": "check_exploration_switch",
            "exploration": "check_exploration_switch",
            "continue_exploration": "check_exploration_switch",
            "checking": "check_exploration",
            "update_direction": "update_exploration_direction",
            "update_direction_pool": "update_exploration_direction_pool",
            "add_to_code_pool": "add_to_exploration_code_pool",
            "submit_for_verification": "queue_verification_request",
            "retire": "check_exploration_switch",
            "create_explorer": "create_workgroup",
            "finish": END,
        },
    )
    graph.add_edge("create_workgroup", "study_framework")
    graph.add_edge("study_framework", "fork_explorer")
    graph.add_edge("fork_explorer", "route_exploration_stage")
    graph.add_edge("wait_direction_quota", "exploration_direction")
    graph.add_edge("exploration_direction", "wait_for_settle")
    graph.add_edge("check_exploration_direction", "wait_for_settle")
    graph.add_edge("exploration", "wait_for_settle")
    graph.add_edge("check_exploration", "wait_for_settle")
    graph.add_edge("wait_for_settle", "check_exploration_switch")
    graph.add_conditional_edges(
        "is_tool_submission",
        lambda workflow_state: workflow_state.get(
            "next_exploration_submission_stage", "exceed_limit_try"
        ),
        {
            "check_exploration_direction": "check_exploration_direction",
            "route_exploration_stage": "route_exploration_stage",
            "check_exploration": "check_exploration",
            "exploration": "exploration",
            "exceed_limit_try": "exceed_limit_try",
            "exceed_explore_try": "exceed_explore_try",
        },
    )
    graph.add_edge("add_to_exploration_direction_pool", "route_exploration_stage")
    graph.add_edge("revise_exploration_direction", "route_exploration_stage")
    graph.add_conditional_edges(
        "check_exploration_switch",
        lambda workflow_state: workflow_state.get(
            "exploration_switch_result", "no_switch"
        ),
        {
            "feedback_received": "preempt_explorer",
            "create_explorer": "create_workgroup",
            "wake_explorer": "wake_explorer",
            "release_explorer_slot": "release_explorer_slot",
            "retire_workgroup": "retire_workgroup",
            "continue_submission": "is_tool_submission",
            "no_switch": "exploration",
        },
    )
    graph.add_edge("preempt_explorer", "wait_for_explorer_attempt_end")
    graph.add_edge("wait_for_explorer_attempt_end", "route_exploration_stage")
    graph.add_edge("update_exploration_direction", "update_exploration_direction_pool")
    graph.add_edge("update_exploration_direction_pool", "route_exploration_stage")
    graph.add_edge("add_to_exploration_code_pool", "route_exploration_stage")
    graph.add_edge("wake_explorer", "route_exploration_stage")
    graph.add_edge("release_explorer_slot", "route_exploration_stage")
    graph.add_edge("retire_workgroup", "release_explorer_slot")
    graph.add_edge("queue_verification_request", END)
    graph.add_edge("exceed_limit_try", "retire_workgroup")
    graph.add_edge("exceed_explore_try", "retire_workgroup")
    return graph
