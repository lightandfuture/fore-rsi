# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Experiment subflow graph for the default workflow."""

from typing import TYPE_CHECKING

from langgraph.graph import StateGraph

if TYPE_CHECKING:
    from ..workflow import DefaultWorkflow


def build_experiment_subflow(workflow: "DefaultWorkflow") -> StateGraph:
    """Build the Experiment subflow graph for the default workflow.

    START --> route_experiment_stage
                +--[initialize_experimenter] --> create_experimenter_workgroup
                |                                --> study_experiment
                |                                --> fork_experimenter [seed = study_experiment, quota = 2]
                |                                     +--[experimenter_1] --> route_experiment_stage[select_resources]
                |                                     +--[experimenter_2] --> route_experiment_stage[select_resources]
                +--[select_resources] ------> lock_select_resources
                |                            --> select_experimenter_resources
                |                            --> wait_for_settle_and_tool_subflow[A=unlock_select_resources,B=select_experimenter_resources,C=abort_resource_selection]
                +--[experiment] ------------> select_experimenter (blocking with quota) --> experiment (running)
                                             --> wait_for_settle_and_tool_subflow[A=publish_result,B=experiment,C=exit_node]

    unlock_select_resources --> END
    abort_resource_selection (release the selection lock without an assignment) --> exit_node
    exit_node --> END
    publish_result --> queue_exploration_feedback --[Command.PARENT]--> route_workflow_stage[exploration]
    """
    return StateGraph(dict)
