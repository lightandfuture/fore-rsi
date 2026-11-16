# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Checker role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class CheckerAgent(BaseAgent):
    """Review plans, work, and conclusions during team collaboration."""

    role_name = "Checker"
