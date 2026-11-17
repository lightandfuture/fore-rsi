# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Default workflow for general-purpose agent collaboration."""

from fore_rsi.rsi_workflows.base_workflow import BaseWorkflow
from fore_rsi.rsi_workflows.custom_workflows.default.agents.checker import (
    CheckerAgent,
)
from fore_rsi.rsi_workflows.custom_workflows.default.agents.coordinator import (
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

    async def run(self) -> None:
        """Run the default team's collaboration workflow."""

