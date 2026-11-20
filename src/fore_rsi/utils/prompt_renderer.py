# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the ForeRSI project

"""Render trusted Jinja prompt templates as plain text."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def render_prompt(template_path: str | Path, context: Mapping[str, object]) -> str:
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
    return environment.get_template(path.name).render(context)


def render_prompt_bundle(
    template_paths: Sequence[str | Path],
    context: Mapping[str, object],
    *,
    section_transition: str | None = None,
) -> str:
    """Render prompt templates in order and join them with an optional transition."""
    rendered_sections = [render_prompt(path, context).strip() for path in template_paths]
    if section_transition is None:
        return "\n\n".join(rendered_sections)
    return f"\n\n{section_transition}\n\n".join(rendered_sections)
