# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Resolve project paths and publish files read by native processes."""

from pathlib import Path
from tempfile import NamedTemporaryFile


def resolve_project_path(path: Path) -> Path:
    """Return an absolute path for application callers, using the working directory outside Git."""
    path = path.expanduser()
    if path.is_absolute():
        return path
    startup_dir = Path.cwd()
    project_root = next(
        (
            directory
            for directory in (startup_dir, *startup_dir.parents)
            if (directory / ".git").exists()
        ),
        startup_dir,
    )
    return (project_root / path).resolve()


def write_private_text(path: Path, text: str) -> None:
    """Publish a complete owner-readable file even when a native process is already reading it."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete_on_close=False) as temporary:
        temporary.write(text)
        temporary.close()
        Path(temporary.name).replace(path)
