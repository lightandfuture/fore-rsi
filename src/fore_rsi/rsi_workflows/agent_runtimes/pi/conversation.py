# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Read Pi's recorded session selection and fork native history without opening a member pane."""

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import NotRequired, TypedDict
from uuid import uuid4

import anyio

from fore_rsi.config import ReasoningEffort


class ObserverEndpoint(TypedDict):
    """Address and private capability for a running member's read-only loopback listener."""

    port: int
    token: str


class ForkPoint(TypedDict):
    """Identify both the last recorded entry and Pi's active parent for the next message."""

    tip: str | None
    leaf: str | None


class PiObservation(TypedDict):
    """Settings shared with the Pi extension; the private endpoint exists only while it is attached."""

    session_file: str
    session_id: str | None
    model: str | None
    effort: ReasoningEffort | None
    endpoint: NotRequired[ObserverEndpoint]
    fork_point: NotRequired[ForkPoint]


def recorded_observation(path: Path, last_report: PiObservation | None) -> PiObservation:
    """Read the recorded branch, retaining a closed editor's selection only for the same history."""
    observation: PiObservation = {"session_file": str(path), "session_id": None, "model": None, "effort": None}
    tip = None
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        return last_report or observation  # Pi may already have an ID before the first persisted message.
    with stream:
        if not (header := stream.readline()):
            return observation
        observation["session_id"] = json.loads(header)["id"]
        # Pi restores from the last entry's ancestor chain, not the last change anywhere in the file.
        selections: dict[str, tuple[str | None, ReasoningEffort | None]] = {}
        for line in stream:
            if not line.endswith(b"\n"):
                break  # An active writer has not committed this entry yet.
            entry = json.loads(line)
            model, effort = selections.get(entry["parentId"], (None, None))
            if entry["type"] == "model_change":
                model = f"{entry['provider']}/{entry['modelId']}"
            elif entry["type"] == "thinking_level_change":
                effort = entry["thinkingLevel"]
            # Assistant messages name the physical model that answered, not the selected virtual model.
            tip = entry["id"]
            selections[tip] = model, effort
            observation["model"], observation["effort"] = model, effort
    if last_report and last_report["session_id"] == observation["session_id"]:
        point = last_report.get("fork_point")
        if point and point["tip"] == tip:
            return last_report
    return observation


async def fork_recording(executable: Path, source: Path, destination: Path, point: ForkPoint | None) -> None:
    """Let Pi copy the recorded tree and establish its parent link before publishing the child's file."""
    with source.open("rb") as stream:
        cwd = json.loads(stream.readline())["cwd"]
    with TemporaryDirectory(dir=destination.parent) as staging:
        sessions = Path(staging) / "sessions"
        # RPC exits on stdin EOF. No prompt, user extensions, MCP connections or provider request
        # are needed to run Pi's native --fork operation. A cancelled copy stays in staging.
        await anyio.run_process(
            [str(executable), "--offline", "--mode", "rpc", "--no-approve", "--no-extensions", "--no-mcp",
             "--no-skills", "--no-context-files", "--no-prompt-templates", "--no-themes",
             "--session-dir", str(sessions), "--fork", str(source)],
            cwd=cwd, env={**os.environ, "PI_CODING_AGENT_DIR": str(Path(staging) / "profile")},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        )
        recording, = sessions.glob("*.jsonl")
        if point is not None:
            await anyio.to_thread.run_sync(_pin_fork_point, recording, point)
        recording.replace(destination)


def _pin_fork_point(path: Path, point: ForkPoint) -> None:
    """Keep the observed prefix of the native clone, including branches, and restore its selected leaf."""
    leaf, tip = point["leaf"], point["tip"]
    with path.open("r+b") as stream:
        stream.readline()  # Keep Pi's new session ID, working directory and parent reference.
        found_leaf = leaf is None
        if tip is not None:
            for line in stream:
                entry_id = json.loads(line)["id"]
                found_leaf |= entry_id == leaf
                if entry_id == tip:
                    break
            else:
                raise ValueError("Pi's recorded history does not contain the observed fork point.")
        if not found_leaf:
            raise ValueError("Pi's selected branch is missing from its recorded history.")
        stream.truncate(stream.tell())  # The parent may have continued while Pi was copying it.
        if leaf != tip:
            # A native custom entry persists a /tree selection without changing the child's model context.
            marker = {"type": "custom", "customType": "fore-rsi.fork", "id": uuid4().hex,
                      "parentId": leaf, "timestamp": datetime.now(UTC).isoformat()}
            stream.write(json.dumps(marker).encode() + b"\n")
