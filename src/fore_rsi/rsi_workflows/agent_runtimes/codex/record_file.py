# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Manage Codex workflow records and profile links."""

import json
import os
from pathlib import Path
from uuid import UUID

from fore_rsi.utils.paths import write_private_text


def link_profile_sessions(link: Path, target: Path) -> None:
    """Expose workflow-owned rollout files through the Codex profile without replacing existing data."""
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except FileExistsError:
        if not link.is_symlink() or link.resolve() != target.resolve():
            raise RuntimeError(f"Codex profile directory is already in use: {link}") from None


def prepare_codex_profile(profile: Path) -> None:
    """Link Codex's user settings and credentials into the workflow-owned profile."""
    origin = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()
    origin.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    if profile.resolve() == origin:
        return

    names = (
        "config.toml",
        "auth.json",
        "AGENTS.md",
        "AGENTS.override.md",
        "rules",
        "skills",
        "hooks.json",
        "hooks",
        "plugins",
        "agents",
        *(path.name for path in origin.glob("*.config.toml")),
    )
    for name in names:
        source, link = origin / name, profile / name
        if link.is_symlink():
            if link.resolve() != source.resolve():
                raise ValueError("This Codex conversation belongs to a different CODEX_HOME.")
        elif not link.exists() and (source.exists() or name == "auth.json"):
            # Codex can write a file-based login through this link without copying credentials.
            link.symlink_to(source, target_is_directory=source.is_dir())


def get_codex_thread(record: Path, sessions: Path) -> str | None:
    """Pin the member's root Codex thread, discovering it only inside its rollout directory."""
    if record.exists():
        return str(UUID(record.read_text(encoding="utf-8").strip()))

    roots: set[str] = set()
    for path in sorted(sessions.rglob("rollout-*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "session_meta":
                    continue
                metadata = entry.get("payload", {})
                if (
                    isinstance(metadata, dict)
                    and metadata.get("id")
                    and not metadata.get("forked_from_id")
                    and not metadata.get("parent_thread_id")
                ):
                    try:
                        roots.add(str(UUID(metadata["id"])))
                    except (TypeError, ValueError):
                        pass
                break

    if len(roots) > 1:
        raise RuntimeError(f"Cannot identify one root Codex conversation in {sessions}.")
    if not roots:
        return None
    thread = roots.pop()
    write_private_text(record, thread + "\n")
    return thread
