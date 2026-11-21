# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Manage Claude Code conversation records and project links."""

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from fore_rsi.utils.paths import write_private_text


def get_claude_project_link(home: Path, conversation: str) -> Path:
    """Return the stable project alias for one Claude Code conversation."""
    return home / "projects" / f"fore-rsi-{UUID(conversation)}"


def link_project_directory(link: Path, target: Path) -> None:
    """Expose a workflow-owned Claude project without replacing an existing project directory."""
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except FileExistsError:
        if not link.is_symlink() or link.resolve() != target.resolve():
            raise RuntimeError(f"Claude project directory is already in use: {link}") from None


def remove_project_link(link: Path, target: Path) -> None:
    """Remove only the Claude project link still owned by this workflow member."""
    if link.is_symlink() and link.resolve() == target.resolve():
        link.unlink()


def prepare_claude_profile(profile: Path) -> None:
    """Reuse user settings and credentials without placing Claude records outside the workflow."""
    origin = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser().resolve()
    origin.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    if profile.resolve() == origin:
        return

    for name in (
        ".credentials.json",
        "settings.json",
        "settings.local.json",
        "CLAUDE.md",
        "commands",
        "hooks",
        "plugins",
        "skills",
    ):
        source, link = origin / name, profile / name
        if link.is_symlink():
            if link.resolve() != source.resolve():
                raise ValueError(f"Claude profile link is already bound to another source: {link}")
        elif not link.exists() and source.exists():
            link.symlink_to(source, target_is_directory=source.is_dir())


def prepare_claude_session(member: Path, profile: Path) -> tuple[str, str, str]:
    """Bind one persistent conversation UUID to its Claude project alias."""
    record = member.with_suffix(".session")
    project_directory = member.parent / "projects" / "agents" / member.name
    try:
        binding = json.loads(record.read_bytes())
    except FileNotFoundError:
        binding = {"id": str(uuid4()), "profile": None}

    conversation = str(UUID(binding["id"]))
    previous_profile = binding.get("profile", binding.get("home"))
    if previous_profile != str(profile):
        if previous_profile is not None:
            remove_project_link(
                get_claude_project_link(Path(previous_profile), conversation), project_directory
            )
        write_private_text(record, json.dumps({"id": conversation, "profile": str(profile)}))

    project_link = get_claude_project_link(profile, conversation)
    link_project_directory(project_link, project_directory)
    flag = "--resume" if (project_directory / f"{conversation}.jsonl").is_file() else "--session-id"
    return project_link.name, flag, conversation
