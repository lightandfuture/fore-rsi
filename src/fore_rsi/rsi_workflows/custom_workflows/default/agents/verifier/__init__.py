# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Compatibility import for callers that still use the former role path."""

from ..experimenter import ExperimenterAgent

VerifierAgent = ExperimenterAgent

__all__ = ["VerifierAgent"]
