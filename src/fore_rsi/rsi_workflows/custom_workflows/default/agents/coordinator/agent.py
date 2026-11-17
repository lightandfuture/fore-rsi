# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Coordinator role for the default collaboration workflow."""

from pathlib import Path

from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.workgroup import Workgroup
from fore_rsi.utils.prompt_renderer import render_prompt


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
        agent_runtime: AgentRuntime,
    ) -> None:
        """Bind the coordinator and render its role instructions without starting execution."""
        super().__init__(agent_name, workgroup, agent_runtime)
        self.system_prompt = render_prompt(
            self.prompt_template_path,
            {
                "role_name": self.role_name,
                "agent_name": self.agent_name,
                "workgroup_name": self.workgroup.workgroup_name,
            },
        )
