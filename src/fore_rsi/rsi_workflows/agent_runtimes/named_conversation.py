# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Native CLIs that select different commands to create and resume a conversation by ID."""

from abc import abstractmethod
from collections.abc import Sequence
from pathlib import Path
import sys

from fore_rsi.config import ReasoningEffort
from fore_rsi.rsi_workflows.agent_runtimes.base import AgentRuntime
from fore_rsi.utils.paths import write_private_text
from fore_rsi.utils.terminal import terminal_executable


class NamedConversationRuntime(AgentRuntime):
    """Keep the pane command stable while the native CLI's launch mode and tool address can change."""

    def build_launch_command(
        self, executable: Path, arguments: Sequence[str] = (), *, system_prompt: str | None = None,
    ) -> list[str]:
        """Prepare a replayable invocation; the PTY child selects the member's native session at exec time."""
        self.harness_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        instructions = self._member_file(".instructions.md")
        if system_prompt is not None:
            write_private_text(instructions, system_prompt)
        options = ["--model", self.agent_config.model] if self.agent_config.model is not None else []
        if self.agent_config.effort is not None:
            options.extend(self._effort_args(self.agent_config.effort))
        if self.tool_mcp is not None:
            options.extend(self._tool_mcp_args())
        # Both helpers use only the standard library. PTY children must not import the
        # working directory or visit editable checkouts via site-packages startup hooks.
        return [
            sys.executable, "-I", "-S", str(terminal_executable().with_name("native_launch.py")),
            self.harness_name, str(executable), str(self._member_file("")), str(self._native_home()),
            str(instructions) if system_prompt is not None else "", *options, *arguments,
        ]

    @abstractmethod
    def _effort_args(self, effort: ReasoningEffort) -> list[str]:
        """Render an explicit per-member reasoning override for the native CLI."""
        ...

    @abstractmethod
    def _native_home(self) -> Path:
        """Return the native profile used to open the interactive session."""
        ...

    def _stdio_server(self) -> dict[str, object]:
        """Connect only this member's tools, including after the workflow host changes ports."""
        bridge = terminal_executable().with_name("tool_stdio.py")
        return {"command": sys.executable, "args": ["-I", "-S", str(bridge), str(self.tool_address_file)]}
