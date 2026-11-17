# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Reuse native CLIs or prepare them with their official user-level installers."""

import asyncio
from collections.abc import Mapping, Sequence
from contextlib import suppress
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from loguru import logger
import psutil


async def ensure_cli_installed(
    command_name: str,
    installed_path: Path,
    installer_url: str,
    *,
    shell: str = "sh",
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return a native CLI launcher for a backend, installing it only when absent."""
    executable = shutil.which(command_name) or shutil.which(str(installed_path))
    if executable is not None:
        return Path(executable).absolute()

    logger.info("Installing {} with its official installer", command_name)
    installer_environment = dict(os.environ)
    if environment is not None:
        installer_environment.update(environment)

    with TemporaryDirectory(prefix=f"fore-rsi-{command_name}-install-") as directory:
        installer = Path(directory) / ("install.ps1" if os.name == "nt" else "install.sh")
        await _run_installation_command(
            [
                "curl.exe" if os.name == "nt" else "curl",
                "--fail", "--silent", "--show-error", "--location",
                "--output", str(installer), installer_url,
            ],
            installer_environment,
        )
        command = (
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
            if os.name == "nt"
            else [shell]
        )
        await _run_installation_command([*command, str(installer)], installer_environment)

    executable = shutil.which(command_name) or shutil.which(str(installed_path))
    if executable is None:
        raise FileNotFoundError(
            f"The {command_name} installer finished without an executable on PATH or at {installed_path}."
        )
    return Path(executable).absolute()


async def _run_installation_command(command: Sequence[str], environment: Mapping[str, str]) -> None:
    """Stream installer output to stderr and wait for its process tree to stop on cancellation."""
    process = await asyncio.create_subprocess_exec(
        *command,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        # A pipe keeps native installers from launching their interactive CLI after installation.
        assert process.stdout is not None
        while output := await process.stdout.read(65536):
            sys.stderr.buffer.write(output)
            sys.stderr.buffer.flush()
        returncode = await process.wait()
    except BaseException:
        children: list[psutil.Process] = []
        try:
            if process.returncode is None:
                with suppress(psutil.NoSuchProcess):
                    children = psutil.Process(process.pid).children(recursive=True)
            for child in children:
                with suppress(psutil.NoSuchProcess):
                    child.terminate()
        finally:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.terminate()
            await process.wait()
            await asyncio.to_thread(psutil.wait_procs, children)
        raise

    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command)
