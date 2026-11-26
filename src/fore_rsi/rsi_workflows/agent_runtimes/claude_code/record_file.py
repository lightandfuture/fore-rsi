# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Manage Claude Code conversation records and project links."""

import json
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


def bind_session_transcript(member: Path, native: Path) -> None:
    """Link the native per-session filename to the member record when using Claude's default profile."""
    record = member.with_suffix(".session")
    binding = json.loads(record.read_bytes())
    conversation = str(UUID(binding["id"]))
    profile = binding.get("native_profile") or binding.get("profile") or binding["home"]
    projects = Path(profile) / "projects"
    directory = member.parent / "projects" / "agents" / member.name
    owned = directory / f"{conversation}.jsonl"
    if native.resolve() == owned.resolve():
        return
    if native.name != owned.name or not native.is_absolute() or native.parent.resolve().parent != projects.resolve():
        raise ValueError(f"Unexpected Claude transcript location for session {conversation}.")
    native.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Install the link before Claude's first write. Never replace an existing
    # native record, even if another session happens to claim the same name.
    native.symlink_to(owned)
    binding["transcript_link"] = str(native)
    write_private_text(record, json.dumps(binding))


def prepare_claude_session(member: Path, profile: Path) -> tuple[dict[str, str], str, str]:
    """Preserve the member UUID and reuse the profile where its conversation was created."""
    record = member.with_suffix(".session")
    directory = member.parent / "projects" / "agents" / member.name
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        binding = json.loads(record.read_bytes())
    except FileNotFoundError:
        binding = {"id": str(uuid4()), "native_profile": str(profile)}
        write_private_text(record, json.dumps(binding))

    conversation = str(UUID(binding["id"]))
    environment = {}
    if "native_profile" not in binding:
        # Existing members keep their project-directory alias and resume settings.
        previous = Path(binding.get("profile") or binding["home"])
        alias = get_claude_project_link(previous, conversation)
        link_project_directory(alias, directory)
        environment = {"CLAUDE_CONFIG_DIR": str(previous), "CLAUDE_CODE_PROJECT_DIR_NAME": alias.name}
    flag = "--resume" if (directory / f"{conversation}.jsonl").is_file() else "--session-id"
    return environment, flag, conversation
