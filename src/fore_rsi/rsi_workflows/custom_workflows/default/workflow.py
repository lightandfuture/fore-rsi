# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow for general-purpose agent collaboration."""

from pathlib import Path

from fore_rsi.config import HarnessConfig, WorkflowConfig
from fore_rsi.rsi_workflows.agent_runtimes import create_agent_runtime
from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow
from fore_rsi.rsi_workflows.custom_workflows.default.agents.checker import (
    CheckerAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator.agent import (
    CoordinatorAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator.tools import create_tools
from fore_rsi.rsi_workflows.custom_workflows.default.agents.explorer import (
    ExplorerAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.verifier import (
    VerifierAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.watchdog import (
    WatchdogAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.worker import (
    WorkerAgent,
)


class DefaultWorkflow(BaseWorkflow):
    """Coordinate a general-purpose agent team's collaboration."""

    workflow_name = "default"
    entry_agent_class = CoordinatorAgent

    # Available roles; each role may have multiple agent instances.
    agent_roles = (
        CoordinatorAgent,
        ExplorerAgent,
        WorkerAgent,
        VerifierAgent,
        CheckerAgent,
        WatchdogAgent,
    )

    def __init__(self, config: WorkflowConfig, session_directory: Path) -> None:
        """Create the default workflow's entry agent without starting native execution."""
        super().__init__(config, session_directory)

        entry_agent_name = f"{self.entry_agent_class.role_name}-01"
        entry_runtime = create_agent_runtime(
            harness_config=HarnessConfig(harness=config.harness),
            session_directory=self.session_directory,
            tool_mcp_host=self.tool_mcp_host,
            tools=create_tools(self.agent_scheduler),
        )
        self.entry_agent = self.create_agent(
            agent_class=self.entry_agent_class,
            agent_name=entry_agent_name,
            workgroup_name=self.global_workgroup.workgroup_name,
            agent_runtime=entry_runtime,
        )

    async def run(self, workspace_id: str) -> None:
        """Start the entry agent and send an optional task-file reference through native input."""
        await self.entry_agent.agent_runtime.start(
            workspace_id,
            terminal_session_name=self.session_directory.name,
            workgroup_name=self.entry_agent.workgroup.workgroup_name,
            agent_name=self.entry_agent.agent_name,
            is_entry=True,
            system_prompt=self.entry_agent.system_prompt,
        )
        if self._config.task is not None:
            await self.entry_agent.agent_runtime.send_message(
                f"Read the following file for the user's task requirements:\n{self._config.task}"
            )
