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
from fore_rsi.rsi_workflows.custom_workflows.default.task import TaskDefinition


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
        self.task_file = session_directory / "task.json"
        self.task: TaskDefinition | None = None
        try:
            saved_task = self.task_file.read_bytes()
        except FileNotFoundError:
            pass
        else:
            self._apply_task(TaskDefinition.model_validate_json(saved_task), persist=False)

        entry_agent_name = f"{self.entry_agent_class.role_name}-01"
        entry_runtime = create_agent_runtime(
            harness_config=HarnessConfig(harness=config.harness),
            session_directory=self.session_directory,
            tool_mcp_host=self.tool_mcp_host,
            tools=self.entry_agent_class.create_tools(self.submit_task),
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

    async def submit_task(self, task: TaskDefinition) -> dict[str, object]:
        """Accept the Coordinator's complete task and return the location of the saved declaration."""
        self._apply_task(task, persist=True)
        return {"task_file": str(self.task_file)}

    def _apply_task(self, task: TaskDefinition, *, persist: bool) -> None:
        """Apply a submitted or restored task without replacing agents, queues, or shared quota entries."""
        roles = {role.role_name for role in self.agent_roles}
        bindings = {(entry.role_name, entry.model) for entry in task.team}
        if len(bindings) != len(task.team):
            raise ValueError("Declare each role and model combination only once.")
        for role_name, _ in bindings:
            if role_name not in roles:
                raise ValueError(f"Unknown agent role {role_name!r}. Available roles: {', '.join(sorted(roles))}.")

        if persist:
            task.save(self.task_file)
        # Only explicit model bindings can become dispatch quotas. Withdrawn bindings
        # stop new dispatches without releasing slots held by running requests.
        if self.task is not None:
            for entry in self.task.team:
                if entry.model is not None and (entry.role_name, entry.model) not in bindings:
                    self.agent_scheduler.set_quota(entry.role_name, entry.model, 0)
        for entry in task.team:
            if entry.model is not None:
                self.agent_scheduler.set_quota(entry.role_name, entry.model, entry.concurrency)
        self.task = task
