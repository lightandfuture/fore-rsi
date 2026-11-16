# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Workgroup identity and membership for workflow agent instances."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fore_rsi.rsi_workflows.base_agent import BaseAgent


class Workgroup:
    """Own the agent instances belonging to one workgroup."""

    def __init__(self, workgroup_name: str) -> None:
        """Initialize an empty workgroup."""
        self.workgroup_name = workgroup_name
        self.agents: dict[str, BaseAgent] = {}
