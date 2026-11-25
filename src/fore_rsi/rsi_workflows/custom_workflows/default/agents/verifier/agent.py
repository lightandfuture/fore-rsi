# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Compatibility import for the former VerifierAgent path."""

from ..experimenter.agent import ExperimenterAgent

VerifierAgent = ExperimenterAgent

__all__ = ["VerifierAgent"]
