# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Coordinator role for the default collaboration workflow."""

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator.tools import (
    bind_submit_task,
)
from fore_rsi.rsi_workflows.workgroup import Workgroup
from fore_rsi.utils.prompt_renderer import render_prompt_bundle

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.custom_workflows.default.workflow import DefaultWorkflow


class CoordinatorAgent(BaseAgent):
    """Handle user requests and coordinate the default workflow's team."""

    role_name = "Coordinator"
    common_system_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "common" / "system.j2"
    )
    common_user_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "common" / "user.j2"
    )
    system_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "coordinator" / "system.j2"
    )
    parse_task_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "coordinator" / "parse_task.j2"
    )

    def __init__(
        self,
        agent_name: str,
        workgroup: Workgroup,
        agent_config: AgentConfig,
        *,
        workflow: "DefaultWorkflow",
    ) -> None:
        """Bind the Coordinator's tools and instructions to this workflow session."""
        submit_task = bind_submit_task(workflow.enqueue_task_submission)
        super().__init__(agent_name, workgroup, agent_config, workflow=workflow, tools=[submit_task])
        prompt_context = {
            "role_name": self.role_name,
            "agent_name": self.agent_name,
            "workgroup_name": self.workgroup.workgroup_name,
        }
        self.system_prompt = render_prompt_bundle(
            [self.common_system_prompt_path, self.system_prompt_path],
            prompt_context,
            section_transition="Here are the Coordinator-specific system instructions.",
        )

    @staticmethod
    async def parse_task(workflow_state: Mapping[str, object]) -> dict[str, object]:
        """Ask the Coordinator to parse the startup task declaration."""
        coordinator = workflow_state["agent"]
        prompt_context = {"startup_task_file": workflow_state["startup_task_file"]}
        user_prompt = render_prompt_bundle(
            [
                CoordinatorAgent.common_user_prompt_path,
                CoordinatorAgent.parse_task_prompt_path,
            ],
            prompt_context,
            section_transition="Here are the Coordinator's instructions for this workflow stage.",
        )
        await coordinator.send_message(user_prompt)
        await coordinator.agent_runtime.wait_until_idle()
        return {}
