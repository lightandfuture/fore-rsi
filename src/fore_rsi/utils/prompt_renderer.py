# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Render trusted Jinja prompt templates as plain text."""

from collections.abc import Iterable, Mapping
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def render_prompt(
    template_path: str | Path,
    context: Mapping[str, object] | None = None,
) -> str:
    """Render a prompt file with variables supplied by workflow or agent callers.

    Includes and inheritance resolve from the template's directory. Missing
    variables raise Jinja's UndefinedError instead of producing empty text.
    """
    path = Path(template_path)
    environment = Environment(
        loader=FileSystemLoader(path.parent),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    return environment.get_template(path.name).render(context or {})


def merge_prompts(prompts: Iterable[str]) -> str:
    """Join already-rendered prompt sections with blank lines."""
    return "\n\n".join(prompt.strip() for prompt in prompts if prompt.strip())
