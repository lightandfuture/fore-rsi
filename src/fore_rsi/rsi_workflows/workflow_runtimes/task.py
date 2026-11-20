# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Accept task submissions from the Coordinator and keep a revision history for each workflow session."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from fore_rsi.rsi_workflows.types import RequiredText
from fore_rsi.rsi_workflows.workflow_runtimes.agent_scheduler import AgentAllocation


class Resource(BaseModel):
    """Declared resource budgets for deployment and the complete experiment set."""

    deployment_resources: dict[str, object] = Field(default_factory=dict)
    experiment_resources: dict[str, object] = Field(default_factory=dict)


class TaskConstraints(BaseModel):
    """Task constraints grouped by their purpose."""

    common_constraints: dict[str, object] = Field(default_factory=dict)
    resources: Resource = Field(default_factory=Resource)
    stop_conditions: list[str] = Field(default_factory=list)
    time_budget: int | float | None = None


class AgentTeam(BaseModel):
    """Role allocations and collaboration notes requested for the task's Agent team."""

    roles: dict[RequiredText, list[AgentAllocation]] = Field(default_factory=dict)
    team_comments: list[str] = Field(default_factory=list)


class TaskSubmission(BaseModel):
    """The task parsed by the Coordinator."""

    # Pydantic validation policy; this is not part of the submitted task payload.
    model_config = ConfigDict(extra="forbid", strict=True)

    goal: RequiredText = Field(description="What the task should achieve.")
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    agent_team: AgentTeam = Field(default_factory=AgentTeam)
    environment_variables: dict[RequiredText, str] = Field(
        default_factory=dict,
        description="Environment variable names and values required by the task.",
    )
    task_comments: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class TaskRevision:
    """One published task and the file that continues to identify it after later submissions."""

    revision_number: int
    revision_file_path: Path
    task_submission: TaskSubmission


class Task:
    """Own task revisions for one workflow session."""

    def __init__(self, session_directory: Path) -> None:
        """Restore task history for one workflow session."""
        self.session_directory = session_directory
        self.current_task: TaskRevision | None = self.read_latest_task_revision()

    def publish_task(self, workflow_state: Mapping[str, object]) -> dict[str, object]:
        """Persist the submitted task and return revision data to the graph."""
        task_submission = workflow_state["task_submission"]
        is_first_task_submission = self.current_task is None
        # LangGraph may replay this node after a downstream failure; reuse the completed revision.
        if (
            self.current_task is not None
            and self.current_task.task_submission == task_submission
        ):
            task_revision = self.current_task
        else:
            next_revision_number = (
                self.current_task.revision_number + 1
                if self.current_task is not None
                else 1
            )
            task_revision = self.write_task_revision(
                next_revision_number,
                task_submission,
            )
        self.current_task = task_revision
        return {
            "task_revision_number": task_revision.revision_number,
            "task_revision_file": str(task_revision.revision_file_path),
            "is_first_task_submission": is_first_task_submission,
        }

    def read_latest_task_revision(self) -> TaskRevision | None:
        """Read the newest published TaskRevision from the session directory."""
        # Task owns this filename pattern, so the numeric suffix is the revision sort key.
        latest_revision_file = max(
            self.session_directory.glob("task_revision_*.json"),
            key=lambda path: int(path.stem.removeprefix("task_revision_")),
            default=None,
        )
        if latest_revision_file is None:
            return None
        revision_number = int(
            latest_revision_file.stem.removeprefix("task_revision_")
        )
        # Convert persisted JSON into the validated domain object used by the workflow.
        task_submission = TaskSubmission.model_validate(
            json.loads(latest_revision_file.read_bytes())
        )
        return TaskRevision(
            revision_number=revision_number,
            revision_file_path=latest_revision_file,
            task_submission=task_submission,
        )

    def write_task_revision(
        self, revision_number: int, task_submission: TaskSubmission
    ) -> TaskRevision:
        """Write one TaskRevision file for this workflow session."""
        self.session_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination = self.session_directory / f"task_revision_{revision_number}.json"
        destination.write_text(
            task_submission.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return TaskRevision(
            revision_number=revision_number,
            revision_file_path=destination,
            task_submission=task_submission,
        )
