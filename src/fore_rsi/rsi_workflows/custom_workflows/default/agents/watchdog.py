# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Watchdog role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class WatchdogAgent(BaseAgent):
    """Observe team progress and follow up on stalled or ineffective work."""

    role_name = "Watchdog"
