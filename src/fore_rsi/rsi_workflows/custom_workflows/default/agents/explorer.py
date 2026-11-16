# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Explorer role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class ExplorerAgent(BaseAgent):
    """Explore approaches for the default workflow's task."""

    role_name = "Explorer"
