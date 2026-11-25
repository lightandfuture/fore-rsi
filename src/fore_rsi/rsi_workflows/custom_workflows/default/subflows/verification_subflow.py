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
                |                            --> fork_verifier [quota = 2]
                |                                 +--[verifier_i]
                |                                        --> route_verification_stage[select_resources]
                +--[select_resources] ------> lock_select_resources
                |                            --> select_verifier_resources
                |                            --> wait_for_settle[A=unlock_select_resources,B=select_verifier_resources]
                +--[verification] ----------> select_verifier
                                             --> verification (experimenting)
                                             --> wait_for_settle[A=publish_result,B=verification]

    unlock_select_resources --> END
    publish_result --> queue_exploration_feedback --> END[exploration]
    """
    return StateGraph(dict)
