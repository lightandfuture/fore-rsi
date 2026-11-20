# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Display the work-progress page for a ForeRSI session."""

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static


class WorkProgressApp(App[None]):
    """Own the progress page's layout and input without controlling the workflow or its terminal server."""

    ENABLE_COMMAND_PALETTE = False

    CSS = """
    #empty {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def __init__(self, session_directory: Path, *, embedded: bool = False) -> None:
        """Bind the page to its session, pane ownership, and terminal locale."""
        super().__init__()
        self._embedded = embedded
        language = next(
            (os.environ[key] for key in ("LC_ALL", "LC_MESSAGES", "LANG") if os.environ.get(key)),
            "",
        )
        chinese = language.lower().startswith("zh")
        self.title = "工作进展" if chinese else "Work progress"
        self.sub_title = session_directory.name
        self._empty_message = "暂无进展数据" if chinese else "No progress data yet"
        self.bind("q", "quit", description="关闭" if chinese else "Close")
        self.bind("escape", "quit", show=False)

    def compose(self) -> ComposeResult:
        """Provide the progress display and a footer for actions the page allows."""
        yield Header()
        yield Static(self._empty_message, id="empty")
        yield Footer()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hide and disable Textual's close actions when the workflow owns the pane."""
        if self._embedded and action in {"quit", "help_quit"}:
            return False
        return super().check_action(action, parameters)
