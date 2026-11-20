# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Shared validation types for workflow declarations."""

from typing import Annotated

from pydantic import StringConstraints


RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
