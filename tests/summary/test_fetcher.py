from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from papersys.summary.fetcher import (
    ArxivContentFetcher,
    ContentUnavailableError,
    FetchResult,
)
from papersys.summary.models import SummarySource
from papersys.summary.conversion import (
    LatexToMarkdownConverter,
    MarkdownExtractionError,
    MarkerMarkdownConverter,
)


class _DummyLatexConverter:
    def __init__(self, *, payload: str) -> None:
        self.payload = payload
        self.called = False

    def convert(self, archive_path: Path) -> str:
        self.called = True
        archive_bytes = archive_path.read_bytes()
        assert archive_bytes, "Latex archive should not be empty"
        return self.payload


class _FailingLatexConverter:
    def convert(self, archive_path: Path) -> str:  # noqa: ARG002 - required signature
        raise MarkdownExtractionError("latex failed")


class _DummyMarkerConverter:
    def __init__(self, *, payload: str) -> None:
        self.payload = payload
        self.called = False

    def convert(self, pdf_path: Path, paper_id: str) -> str:
        self.called = True
        assert pdf_path.exists(), "PDF should exist for marker conversion"
        return self.payload


class _FailingMarkerConverter:
    def convert(self, pdf_path: Path, paper_id: str) -> str:  # noqa: ARG002 - required signature
        raise MarkdownExtractionError("marker failed")


def _fake_http_get(url: str, *, timeout: int = 30) -> bytes:  # noqa: ARG001
    if url.endswith(".pdf"):
        return b"%PDF-stub"
    return b"TAR-STUB"


@pytest.fixture()
def summary_source() -> SummarySource:
    return SummarySource(
        paper_id="2501.12345",
        title="Synthetic Data Generation",
        abstract="We explore markdown extraction",
    )


def test_fetcher_prefers_latex(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, summary_source: SummarySource) -> None:
    monkeypatch.setattr("papersys.summary.fetcher._http_get", _fake_http_get)
    latex_converter = _DummyLatexConverter(payload="LATEX-MD")
    marker_converter = _FailingMarkerConverter()

    fetcher = ArxivContentFetcher(
        pdf_dir=tmp_path / "data",
        delay=0,
        max_retry=1,
        fetch_latex_source=True,
        latex_converter=cast(LatexToMarkdownConverter, latex_converter),
        marker_converter=cast(MarkerMarkdownConverter, marker_converter),
    )

    result: FetchResult = fetcher.fetch(summary_source)

    assert result.markdown_context == "LATEX-MD"
    assert latex_converter.called is True


def test_fetcher_falls_back_to_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, summary_source: SummarySource) -> None:
    monkeypatch.setattr("papersys.summary.fetcher._http_get", _fake_http_get)
    marker_converter = _DummyMarkerConverter(payload="MARKER-MD")

    fetcher = ArxivContentFetcher(
        pdf_dir=tmp_path / "data",
        delay=0,
        max_retry=1,
        fetch_latex_source=True,
        latex_converter=cast(LatexToMarkdownConverter, _FailingLatexConverter()),
        marker_converter=cast(MarkerMarkdownConverter, marker_converter),
    )

    result = fetcher.fetch(summary_source)

    assert result.markdown_context == "MARKER-MD"
    assert marker_converter.called is True


def test_fetcher_skips_when_all_converters_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    summary_source: SummarySource,
) -> None:
    monkeypatch.setattr("papersys.summary.fetcher._http_get", _fake_http_get)

    fetcher = ArxivContentFetcher(
        pdf_dir=tmp_path / "data",
        delay=0,
        max_retry=1,
        fetch_latex_source=True,
        latex_converter=cast(LatexToMarkdownConverter, _FailingLatexConverter()),
        marker_converter=cast(MarkerMarkdownConverter, _FailingMarkerConverter()),
    )

    with pytest.raises(ContentUnavailableError):
        fetcher.fetch(summary_source)
