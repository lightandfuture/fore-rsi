# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Worker role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class WorkerAgent(BaseAgent):
    """Carry out assigned work and produce artifacts for verification."""

    role_name = "Worker"
