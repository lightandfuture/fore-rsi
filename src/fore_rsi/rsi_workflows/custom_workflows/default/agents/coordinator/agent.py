# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Coordinator role for the default collaboration workflow."""

from pathlib import Path
from typing import TYPE_CHECKING

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator.tools import (
    bind_submit_task,
)
from fore_rsi.rsi_workflows.workgroup import Workgroup
from fore_rsi.utils.prompt_renderer import render_prompt

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.custom_workflows.default.workflow import DefaultWorkflow


class CoordinatorAgent(BaseAgent):
    """Handle user requests and coordinate the default workflow's team."""

    role_name = "Coordinator"
    prompt_template_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "coordinator" / "system.j2"
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
        self.system_prompt = render_prompt(
            self.prompt_template_path,
            {
                "role_name": self.role_name,
                "agent_name": self.agent_name,
                "workgroup_name": self.workgroup.workgroup_name,
            },
        )
