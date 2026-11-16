# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Resolve application paths relative to the current project's repository root."""

from pathlib import Path


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
