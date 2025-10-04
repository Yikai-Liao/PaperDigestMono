"""Rendering helpers for markdown summaries."""

from __future__ import annotations

from typing import List
from pathlib import Path
import polars as pl

from jinja2 import Environment, BaseLoader

from .models import SummaryDocument


_DEFAULT_TEMPLATE = """---
title: "{{ title }}"
date: {{ updated_at }}
draft: {{ draft }}
---

# {{ title }}
**Paper ID:** {{ paper_id }}
**Language:** {{ language }}
**Authors:** {{ authors }}
**Abstract:** {{ abstract }}

{% for heading, body in sections.items() %}
## {{ heading }}

{{ body.strip() }}

{% endfor %}

[Read full paper](https://arxiv.org/abs/{{ paper_id }})
"""


class SummaryRenderer:
    """Render structured documents into Markdown strings."""

    def __init__(self, template: str | None = None) -> None:
        env = Environment(loader=BaseLoader(), autoescape=False, trim_blocks=True, lstrip_blocks=True)
        self._template = env.from_string(template or _DEFAULT_TEMPLATE)

    def render(self, document: SummaryDocument, draft: bool = False, authors: str = "", abstract: str = "", updated_at: str = "") -> str:
        return self._template.render(
            title=document.title,
            paper_id=document.paper_id,
            language=document.language,
            sections=document.sections,
            draft=str(draft).lower(),
            authors=authors,
            abstract=abstract,
            updated_at=updated_at,
        ).strip() + "\n"

    def build_site(self, documents: List[SummaryDocument], output_dir: Path, preferences_df: Optional[pl.DataFrame] = None) -> None:
        """
        Batch render summaries to Markdown files in output_dir.
        Sets draft status based on preferences if provided.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for doc in documents:
            arxiv_id = doc.paper_id
            # Get preference
            if preferences_df is not None:
                pref_row = preferences_df.filter(pl.col("arxiv_id") == arxiv_id)
                preference = pref_row["preference"].item() if len(pref_row) > 0 else "neutral"
                draft = preference == "dislike"
            else:
                draft = False

            # Assume authors, abstract, updated_at from doc or external
            authors = getattr(doc, "authors", "")
            abstract = getattr(doc, "abstract", "")
            updated_at = getattr(doc, "updated_at", "")

            rendered = self.render(doc, draft=draft, authors=authors, abstract=abstract, updated_at=updated_at)

            output_path = output_dir / f"{arxiv_id}.md"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(rendered)

            logger.info(f"Rendered {arxiv_id} to {output_path}")


__all__ = ["SummaryRenderer"]
