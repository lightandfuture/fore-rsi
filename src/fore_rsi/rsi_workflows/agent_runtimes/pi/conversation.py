# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Read Pi's recorded session state without opening a member pane."""

import json
from pathlib import Path
from typing import NotRequired, TypedDict

from fore_rsi.config import ReasoningEffort


class IpcEndpoint(TypedDict):
    """Address and private capability for a running member's local IPC listener."""

    token: str
    socket_path: NotRequired[str]
    port: NotRequired[int]


class PiObservation(TypedDict):
    """Session settings returned by the running Pi extension or recorded conversation."""

    session_file: str
    session_id: str | None
    model: str | None
    effort: ReasoningEffort | None


def recorded_observation(path: Path) -> PiObservation:
    """Read the selected model and effort from a saved Pi record file."""
    observation: PiObservation = {
        "session_file": str(path),
        "session_id": None,
        "model": None,
        "effort": None,
    }
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        return observation
    with stream:
        if not (header := stream.readline()):
            return observation
        observation["session_id"] = json.loads(header)["id"]
        # Pi restores from the last entry's ancestor chain, not the last change anywhere in the file.
        selections: dict[str, tuple[str | None, ReasoningEffort | None]] = {}
        for line in stream:
            if not line.endswith(b"\n"):
                break
            entry = json.loads(line)
            model, effort = selections.get(entry["parentId"], (None, None))
            if entry["type"] == "model_change":
                model = f"{entry['provider']}/{entry['modelId']}"
            elif entry["type"] == "thinking_level_change":
                effort = entry["thinkingLevel"]
            selections[entry["id"]] = model, effort
            observation["model"], observation["effort"] = model, effort
    return observation
