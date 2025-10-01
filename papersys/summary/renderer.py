"""Rendering helpers for markdown summaries."""

from __future__ import annotations

from jinja2 import Environment, BaseLoader

from .models import SummaryDocument


_DEFAULT_TEMPLATE = """# {{ title }}
**Paper ID:** {{ paper_id }}
**Language:** {{ language }}

{% for heading, body in sections.items() %}
## {{ heading }}

{{ body.strip() }}

{% endfor %}
"""


class SummaryRenderer:
    """Render structured documents into Markdown strings."""

    def __init__(self, template: str | None = None) -> None:
        env = Environment(loader=BaseLoader(), autoescape=False, trim_blocks=True, lstrip_blocks=True)
        self._template = env.from_string(template or _DEFAULT_TEMPLATE)

    def render(self, document: SummaryDocument) -> str:
        return self._template.render(
            title=document.title,
            paper_id=document.paper_id,
            language=document.language,
            sections=document.sections,
        ).strip() + "\n"


__all__ = ["SummaryRenderer"]
