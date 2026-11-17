# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""The task requirements submitted to the default workflow by its Coordinator."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, StringConstraints


type RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TeamRequirement(BaseModel):
    """Requested concurrent workers for one role, optionally using a specific model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role_name: RequiredText
    concurrency: NonNegativeInt | Literal["unlimited"]
    model: RequiredText | None = Field(default=None, description="Omit when the task does not specify a model.")


class TaskDefinition(BaseModel):
    """User intent and declared allowances, separate from discovered capacity and execution state."""

    model_config = ConfigDict(extra="forbid", strict=True)

    description: RequiredText = Field(description="What the user wants the team to achieve.")
    constraints: list[str] = Field(default_factory=list, description="Conditions the work must preserve.")
    resources: list[str] = Field(default_factory=list, description="Authorized resources, scope, and limits.")
    inputs: list[str] = Field(default_factory=list, description="References to files or other task materials.")
    deliverables: list[str] = Field(default_factory=list, description="Expected outputs and acceptance criteria.")
    time_budget_seconds: NonNegativeInt | None = None
    team: list[TeamRequirement] = Field(default_factory=list)

    def save(self, path: Path) -> None:
        """Replace the session's task declaration only after the complete submission is written."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
        temporary_path = Path(temporary.name)
        try:
            with temporary:
                temporary.write(self.model_dump_json(indent=2) + "\n")
            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
