# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Parse and validate ForeRSI CLI inputs and report usage errors."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Annotated

import tyro

from fore_rsi.cli.validation import validate_config
from fore_rsi.config import Config


@dataclass
class _CommandLine:
    # Show the installed ForeRSI version and exit.
    version: Annotated[bool, tyro.conf.arg(help_behavior_hint="")] = False
    options: Annotated[Config, tyro.conf.arg(name="")] = field(default_factory=Config)


def parse_args(args: Sequence[str] | None = None) -> Config:
    """Return validated configuration, or exit after help, version, or a usage error."""
    command_line = tyro.cli(
        _CommandLine,
        prog="fore-rsi",
        description="Run agent teams with feedback-driven workflows.",
        args=args,
        config=(tyro.conf.DisallowNone, tyro.conf.FlagCreatePairsOff),
    )
    if command_line.version:
        print(f"fore-rsi {version('fore-rsi')}")
        raise SystemExit(0)

    validate_config(command_line.options)
    return command_line.options
