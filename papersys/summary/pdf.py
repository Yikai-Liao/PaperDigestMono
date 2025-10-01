"""Utilities for retrieving and storing PDFs used in the summary pipeline."""

from __future__ import annotations

from pathlib import Path
from time import sleep

from loguru import logger

from .models import SummarySource


class PdfFetcher:
    """Best-effort PDF retriever.

    The real system would fetch remote content. For the initial skeleton we emulate the
    behaviour by creating placeholder PDFs so that downstream components can be exercised
    in tests and during local dry runs.
    """

    def __init__(self, output_dir: Path, *, delay: int, max_retry: int) -> None:
        self._output_dir = output_dir
        self._delay = max(delay, 0)
        self._max_retry = max(max_retry, 1)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, source: SummarySource) -> Path:
        target = self._output_dir / f"{source.paper_id}.pdf"
        attempt = 0
        while attempt < self._max_retry:
            attempt += 1
            try:
                logger.debug("Creating placeholder PDF for {} at {}", source.paper_id, target)
                target.write_bytes(_placeholder_pdf_bytes(source))
                return target
            except OSError as exc:  # pragma: no cover - defensive; unlikely in tests
                logger.warning("Failed to write PDF for {} on attempt {}: {}", source.paper_id, attempt, exc)
                sleep(self._delay)
        raise RuntimeError(f"Unable to create PDF for {source.paper_id} after {self._max_retry} attempts")


def _placeholder_pdf_bytes(source: SummarySource) -> bytes:
    header = "%PDF-1.4\n% Summaries placeholder\n"
    body = (
        f"Paper: {source.paper_id}\nTitle: {source.title}\n"
        f"Abstract: {source.abstract[:200]}\n"
    )
    footer = "%%EOF\n"
    return (header + body + footer).encode("utf-8")


__all__ = ["PdfFetcher"]
