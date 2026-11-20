# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Verifier role for the default collaboration workflow."""

from fore_rsi.rsi_workflows.base_agent import BaseAgent


class VerifierAgent(BaseAgent):
    """Gather feedback and evidence about the team's work against task objectives."""

    role_name = "Verifier"
