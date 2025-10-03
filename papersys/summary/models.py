"""Data models used by the summary pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SummarySource:
    """Minimal metadata required to summarise a single paper."""

    paper_id: str
    title: str
    abstract: str
    pdf_url: str | None = None
    language: str | None = None
    score: float | None = None
    categories: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class SummaryDocument:
    """Structured summary content produced by the generator."""

    paper_id: str
    title: str
    language: str
    sections: dict[str, str] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines: list[str] = [f"# {self.title}", "", f"**Paper ID:** {self.paper_id}", ""]
        if self.language:
            lines.append(f"**Language:** {self.language}")
            lines.append("")
        for heading, body in self.sections.items():
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(body.strip())
            lines.append("")
        return "\n".join(lines).strip()


@dataclass(slots=True)
class SummaryArtifact:
    """Filesystem artefacts produced for a single summary."""

    source: SummarySource
    pdf_path: Path
    markdown_path: Path
    document: SummaryDocument
    markdown: str


__all__ = ["SummarySource", "SummaryDocument", "SummaryArtifact"]
