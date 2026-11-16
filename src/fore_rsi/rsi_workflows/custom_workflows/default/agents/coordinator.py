# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Coordinator role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class CoordinatorAgent(BaseAgent):
    """Handle user requests and coordinate the default workflow's team."""

    role_name = "Coordinator"
