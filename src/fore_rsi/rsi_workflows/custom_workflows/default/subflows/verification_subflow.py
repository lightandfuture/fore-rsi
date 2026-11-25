# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Verifier subflow graph for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_verification_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the Verifier subflow graph for the default workflow.

    START --> route_verification_stage
                +--[initialize_verifier] --> create_verifier_workgroup
                |                            --> study_verification
                |                            --> fork_verifier [seed = study_verification, quota = 2]
                |                                 +--[verifier_1] --> route_verification_stage[select_resources]
                |                                 +--[verifier_2] --> route_verification_stage[select_resources]
                +--[select_resources] ------> lock_select_resources
                |                            --> select_verifier_resources
                |                            --> wait_for_settle_and_tool_subflow[A=unlock_select_resources,B=select_verifier_resources,C=abort_resource_selection]
                +--[verification] ----------> select_verifier (blocking with quota) --> verification (experimenting)
                |                            --> wait_for_settle_and_tool_subflow[A=publish_result,B=verification,C=END]

    unlock_select_resources --> END
    abort_resource_selection (release the selection lock without an assignment) --> END
    publish_result --> queue_exploration_feedback --> END[exploration]
    """
    return StateGraph(dict)
