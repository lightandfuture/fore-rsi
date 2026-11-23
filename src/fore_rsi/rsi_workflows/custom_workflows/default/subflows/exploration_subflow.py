# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Explorer subflow graph for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_exploration_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the Explorer subflow graph for the current task."""
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
        "sleep_explorer",
        "wake_explorer",
        "exploration",
        "check_exploration",
        "queue_verification_request",
        "release_explorer_slot",
    ):
        graph.add_node(node_name, lambda workflow_state: {})

    # START --> route_exploration_stage
    #             +--[initialize_explorer] --> create_workgroup
    #             |                            |
    #             |                            v
    #             |                      study_framework
    #             |                            |
    #             |                            v
    #             |                      fork_explorer [seed = study_framework, forks = 4]
    #             |                            +--[fork_1] --> route_exploration_stage
    #             |                            +--[fork_2] --> route_exploration_stage
    #             |                            +--[fork_3] --> route_exploration_stage
    #             |                            +--[fork_4] --> route_exploration_stage
    #             +--[select_direction] ------> wait_direction_quota
    #             |                            --> exploration_direction
    #             |                            --> route_exploration_stage
    #             +--[checking_direction] ------> check_exploration_direction
    #             |                            --> route_exploration_stage
    #             +--[direction_rejected] ----> revise_exploration_direction
    #             |                            --> route_exploration_stage
    #             +--[direction_confirmed] ---> add_to_exploration_direction_pool
    #             |                            --> route_exploration_stage
    #             +--[exploration] ------------> exploration
    #             |                            --> route_exploration_stage
    #             +--[checking] ---------------> check_exploration
    #             |                            --> route_exploration_stage
    #             +--[revise_exploration] ----> revise_exploration
    #             |                            --> route_exploration_stage
    #             +--[submit_for_verification] -> queue_verification_request
    #                                          +--> release_explorer_slot
    #                                          |    --> route_exploration_stage
    #                                          +--> END
    #             +--[switch_exploration] ----> check_exploration_switch
    #                                          +--[feedback_received / preempt]
    #                                          |      --> preempt_explorer
    #                                          |      --> wait_for_explorer_attempt_end
    #                                          |      --> route_exploration_stage
    #                                          +--[create_explorer: quota, no queue]
    #                                          |      --> create_workgroup
    #                                          |      --> fork_explorer
    #                                          |      --> route_exploration_stage
    #                                          +--[wake_explorer: quota + queue]
    #                                          |      --> wake_explorer
    #                                          |      --> route_exploration_stage
    #                                          +--[no_switch]
    #                                                 --> route_exploration_stage
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
            "switch_exploration": "check_exploration_switch",
            "exploration": "exploration",
            "checking": "check_exploration",
            "revise_exploration": "exploration",
            "submit_for_verification": "queue_verification_request",
        },
    )
    graph.add_edge("create_workgroup", "study_framework")
    graph.add_edge("study_framework", "fork_explorer")
    graph.add_edge("fork_explorer", "route_exploration_stage")
    graph.add_edge("wait_direction_quota", "exploration_direction")
    graph.add_edge("exploration_direction", "route_exploration_stage")
    graph.add_edge(
        "check_exploration_direction",
        "route_exploration_stage",
    )
    graph.add_edge(
        "add_to_exploration_direction_pool",
        "route_exploration_stage",
    )
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
            "no_switch": "route_exploration_stage",
        },
    )
    graph.add_edge("preempt_explorer", "wait_for_explorer_attempt_end")
    graph.add_edge("wait_for_explorer_attempt_end", "route_exploration_stage")
    graph.add_edge("exploration", "route_exploration_stage")
    graph.add_edge("check_exploration", "route_exploration_stage")
    graph.add_edge("queue_verification_request", "release_explorer_slot")
    graph.add_edge("queue_verification_request", END)
    graph.add_edge("release_explorer_slot", "route_exploration_stage")
    graph.add_edge("sleep_explorer", END)
    graph.add_edge("wake_explorer", "route_exploration_stage")
    return graph
