# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Coordinator role for the default collaboration workflow."""

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, cast

from fore_rsi.config import AgentConfig
from fore_rsi.rsi_workflows.agent_runtimes.tool_mcp import register_agent_tool
from fore_rsi.rsi_workflows.base_agent import BaseAgent
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator.tools import (
    submit_task,
)
from fore_rsi.rsi_workflows.custom_workflows.default.subflows.general_subflow import (
    enqueue_task_submission,
)
from fore_rsi.rsi_workflows.workgroup import Workgroup
from fore_rsi.utils.prompt_renderer import merge_prompts, render_prompt

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
        submit_task_tool = register_agent_tool(
            submit_task,
            submit_task_operation=partial(enqueue_task_submission, workflow),
        )
        super().__init__(
            agent_name,
            workgroup,
            agent_config,
            workflow=workflow,
            tools=[submit_task_tool],
        )
        prompt_context = {
            "role_name": self.role_name,
            "agent_name": self.agent_name,
            "workgroup_name": self.workgroup.workgroup_name,
        }
        self.system_prompt = merge_prompts(
            [
                render_prompt(self.common_system_prompt_path),
                render_prompt(self.system_prompt_path, prompt_context),
            ]
        )

    @staticmethod
    async def parse_task(workflow_state: Mapping[str, object]) -> dict[str, object]:
        """Ask the Coordinator to parse the startup task declaration."""
        coordinator_agent = cast(CoordinatorAgent, workflow_state["agent"])
        prompt_context = {"startup_task_file": workflow_state["startup_task_file"]}
        user_prompt = merge_prompts(
            [
                render_prompt(CoordinatorAgent.common_user_prompt_path),
                render_prompt(CoordinatorAgent.parse_task_prompt_path, prompt_context),
            ]
        )
        await coordinator_agent.send_message(user_prompt, mode="queue")
        return {}
