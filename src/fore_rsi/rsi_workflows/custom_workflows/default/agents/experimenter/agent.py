# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Experimenter role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class ExperimenterAgent(BaseAgent):
    """Run assigned experiments and report evidence against task objectives."""

    role_name = "Experimenter"
