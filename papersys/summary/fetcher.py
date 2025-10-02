"""Fetch PDF/Markdown resources for summary generation."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from loguru import logger

from .conversion import (
    LatexToMarkdownConverter,
    MarkdownExtractionError,
    MarkerMarkdownConverter,
)
from .models import SummarySource


USER_AGENT = "PaperDigestMono/0.1 (+https://github.com/Yikai-Liao/PaperDigestMono)"


def _http_get(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # type: ignore[no-untyped-call]
        return response.read()


def _basic_context(source: SummarySource) -> str:
    parts = [
        f"Title: {source.title}",
        f"Abstract: {source.abstract}",
    ]
    return "\n\n".join(parts).strip()


@dataclass(slots=True)
class FetchResult:
    pdf_path: Path
    markdown_context: str


class ContentUnavailableError(RuntimeError):
    """Raised when a paper cannot provide usable Markdown content."""


class SummaryContentFetcher(Protocol):
    def fetch(self, source: SummarySource) -> FetchResult:
        """Download supporting artefacts for ``source`` and return file paths."""


@dataclass(slots=True)
class StubContentFetcher:
    output_dir: Path

    def fetch(self, source: SummarySource) -> FetchResult:
        target = self.output_dir / f"{source.paper_id}.pdf"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_placeholder_pdf_bytes(source))
        logger.debug("Stub PDF created for %s at %s", source.paper_id, target)
        return FetchResult(pdf_path=target, markdown_context=_basic_context(source))


def _placeholder_pdf_bytes(source: SummarySource) -> bytes:
    header = "%PDF-1.4\n% Stub summary PDF\n"
    body = (
        f"Paper: {source.paper_id}\nTitle: {source.title}\n"
        f"Abstract: {source.abstract[:200]}\n"
    )
    footer = "%%EOF\n"
    return (header + body + footer).encode("utf-8")


@dataclass(slots=True)
class ArxivContentFetcher:
    pdf_dir: Path
    delay: int
    max_retry: int
    fetch_latex_source: bool
    latex_converter: LatexToMarkdownConverter | None = None
    marker_converter: MarkerMarkdownConverter | None = None
    marker_timeout: int = 180
    _latex_dir: Path = field(init=False, repr=False)
    _latex_converter_failed: bool = field(init=False, default=False, repr=False)
    _marker_unavailable: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self._latex_dir = self.pdf_dir / "latex"
        if self.fetch_latex_source:
            self._latex_dir.mkdir(parents=True, exist_ok=True)
        if self.marker_converter is None:
            self.marker_converter = MarkerMarkdownConverter(timeout=self.marker_timeout)

    def fetch(self, source: SummarySource) -> FetchResult:  # noqa: D401 - docstring inherited
        pdf_path = self._download_pdf(source)
        markdown: str | None = None

        if self.fetch_latex_source:
            archive_path = self._download_latex_archive(source)
            if archive_path is not None:
                markdown = self._convert_latex_archive(archive_path, source.paper_id)

        if markdown is None:
            markdown = self._convert_pdf_with_marker(pdf_path, source.paper_id)

        if markdown is None:
            logger.error(
                "Skipping %s: failed to extract Markdown from LaTeX and PDF sources",
                source.paper_id,
            )
            raise ContentUnavailableError(f"Unable to extract Markdown for {source.paper_id}")

        assert markdown is not None
        return FetchResult(pdf_path=pdf_path, markdown_context=markdown)

    # ------------------------------------------------------------------
    def _download_pdf(self, source: SummarySource) -> Path:
        target = self.pdf_dir / f"{source.paper_id}.pdf"
        if target.exists():
            return target

        url = source.pdf_url or f"https://arxiv.org/pdf/{source.paper_id}.pdf"
        last_error: Exception | None = None
        for attempt in range(1, self.max_retry + 1):
            try:
                logger.info("Downloading PDF for %s (attempt %d)", source.paper_id, attempt)
                data = _http_get(url)
                target.write_bytes(data)
                return target
            except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
                last_error = exc
                logger.warning("PDF fetch failed for %s: %s", source.paper_id, exc)
                if attempt < self.max_retry and self.delay:
                    time.sleep(self.delay)
        raise RuntimeError(f"Failed to download PDF for {source.paper_id}: {last_error}")

    def _download_latex_archive(self, source: SummarySource) -> Path | None:
        target = self._latex_dir / f"{source.paper_id}.tar"
        if target.exists():
            return target
        url = f"https://export.arxiv.org/e-print/{source.paper_id}"
        try:
            logger.info("Downloading LaTeX source for %s", source.paper_id)
            payload = _http_get(url)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            logger.warning("Failed to download LaTeX for %s: %s", source.paper_id, exc)
            return None
        target.write_bytes(payload)
        return target

    def _convert_latex_archive(self, archive_path: Path, paper_id: str) -> str | None:
        converter = self._get_latex_converter()
        if converter is None:
            return None
        try:
            return converter.convert(archive_path)
        except MarkdownExtractionError as exc:
            logger.warning("LaTeX conversion failed for %s: %s", paper_id, exc)
            return None

    def _convert_pdf_with_marker(self, pdf_path: Path, paper_id: str) -> str | None:
        if self._marker_unavailable:
            return None
        converter = self._get_marker_converter()
        if converter is None:
            self._marker_unavailable = True
            return None
        try:
            return converter.convert(pdf_path, paper_id)
        except MarkdownExtractionError as exc:
            logger.warning("Marker conversion failed for %s: %s", paper_id, exc)
            self._marker_unavailable = True
            return None

    def _get_latex_converter(self) -> LatexToMarkdownConverter | None:
        if self._latex_converter_failed:
            return None
        if self.latex_converter is not None:
            return self.latex_converter
        try:
            self.latex_converter = LatexToMarkdownConverter()
        except MarkdownExtractionError as exc:
            logger.warning("Unable to initialise latex2json converter: %s", exc)
            self._latex_converter_failed = True
            return None
        return self.latex_converter

    def _get_marker_converter(self) -> MarkerMarkdownConverter | None:
        if self.marker_converter is not None:
            return self.marker_converter
        try:
            self.marker_converter = MarkerMarkdownConverter(
                timeout=self.marker_timeout,
            )
        except Exception as exc:  # pragma: no cover - constructor expected to succeed
            logger.warning("Unable to initialise marker converter: %s", exc)
            return None
        return self.marker_converter


__all__ = [
    "FetchResult",
    "ContentUnavailableError",
    "SummaryContentFetcher",
    "StubContentFetcher",
    "ArxivContentFetcher",
]
