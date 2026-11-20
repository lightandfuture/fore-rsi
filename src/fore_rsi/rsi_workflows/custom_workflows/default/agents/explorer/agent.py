# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Explorer role and workflow stages for the default collaboration workflow."""

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.workgroup import Workgroup
from fore_rsi.utils.prompt_renderer import render_prompt_bundle

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.custom_workflows.default.workflow import DefaultWorkflow


class ExplorerAgent(BaseAgent):
    """Explore approaches for the default workflow's task."""

    role_name = "Explorer"
    common_system_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "common" / "system.j2"
    )
    common_user_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "common" / "user.j2"
    )
    system_prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / "explorer" / "system.j2"
    )
    study_initial_context_prompt_path = (
        Path(__file__).resolve().parents[2]
        / "prompts"
        / "explorer"
        / "study_initial_context.j2"
    )

    def __init__(
        self,
        agent_name: str,
        workgroup: Workgroup,
        agent_config: AgentConfig,
        *,
        workflow: "DefaultWorkflow",
    ) -> None:
        """Bind the Explorer's system prompt to its role and workflow identity."""
        super().__init__(agent_name, workgroup, agent_config, workflow=workflow)
        prompt_context = {
            "role_name": self.role_name,
            "agent_name": self.agent_name,
            "workgroup_name": self.workgroup.workgroup_name,
        }
        self.system_prompt = render_prompt_bundle(
            [self.common_system_prompt_path, self.system_prompt_path],
            prompt_context,
            section_transition="Here are the Explorer-specific system instructions.",
        )

    @staticmethod
    async def study_initial_context(workflow_state: Mapping[str, object]) -> dict[str, object]:
        """Study the task context before defining the initial baseline."""
        explorer = workflow_state["agent"]
        user_prompt = render_prompt_bundle(
            [
                ExplorerAgent.common_user_prompt_path,
                ExplorerAgent.study_initial_context_prompt_path,
            ],
            {"task_revision_file": workflow_state["task_revision_file"]},
            section_transition="Here are the Explorer's instructions for this workflow stage.",
        )
        await explorer.send_message(user_prompt)
        await explorer.agent_runtime.wait_until_idle()
        return {}
