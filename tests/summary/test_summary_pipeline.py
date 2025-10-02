from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import AppConfig
from papersys.config.llm import LLMConfig
from papersys.config.summary import PdfFetchConfig, SummaryLLMConfig, SummaryPipelineConfig
from papersys.summary import SummaryPipeline, SummarySource
from papersys.summary.fetcher import ContentUnavailableError, FetchResult


def _build_app_config(tmp_path: Path) -> AppConfig:
    summary_cfg = SummaryPipelineConfig(
        pdf=PdfFetchConfig(
            output_dir="summary-output",
            delay=0,
            max_retry=1,
            fetch_latex_source=False,
        ),
        llm=SummaryLLMConfig(
            model="demo-llm",
            language="en",
            enable_latex=False,
        ),
    )
    llm_cfg = LLMConfig(
        alias="demo-llm",
        name="StubModel",
        base_url="http://localhost",
        api_key="dummy",
        temperature=0.2,
        top_p=0.9,
        num_workers=1,
        reasoning_effort=None,
    )
    return AppConfig(
        data_root=tmp_path,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        ingestion=None,
        embedding=None,
        scheduler=None,
        backup=None,
        recommend_pipeline=None,
        summary_pipeline=summary_cfg,
        llms=[llm_cfg],
    )


def test_summary_pipeline_generates_artifacts(tmp_path: Path) -> None:
    config = _build_app_config(tmp_path)
    pipeline = SummaryPipeline(config, base_path=tmp_path)

    sources = [
        SummarySource(
            paper_id="2501.00001",
            title="Towards Robust Summaries",
            abstract="We propose a pipeline that combines retrieval, reasoning, and rendering.",
        )
    ]

    artifacts = pipeline.run(sources)

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.pdf_path.exists(), "PDF should be created"
    assert artifact.markdown_path.exists(), "Markdown output should be created"
    markdown_text = artifact.markdown_path.read_text(encoding="utf-8")
    assert "Towards Robust Summaries" in markdown_text
    assert "Highlights" in markdown_text


def test_summary_pipeline_dry_run(tmp_path: Path) -> None:
    config = _build_app_config(tmp_path)
    pipeline = SummaryPipeline(config, base_path=tmp_path)

    artifacts = pipeline.run([], dry_run=True)

    assert artifacts == []
    sources = pipeline.describe_sources()
    assert sources.pdf_dir.exists()
    assert sources.markdown_dir.exists()


def test_summary_pipeline_requires_known_llm(tmp_path: Path) -> None:
    summary_cfg = SummaryPipelineConfig(
        pdf=PdfFetchConfig(
            output_dir="summary-output",
            delay=0,
            max_retry=1,
            fetch_latex_source=False,
        ),
        llm=SummaryLLMConfig(
            model="missing-llm",
            language="en",
            enable_latex=False,
        ),
    )
    config = AppConfig(
        data_root=tmp_path,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        ingestion=None,
        embedding=None,
        scheduler=None,
        backup=None,
        recommend_pipeline=None,
        summary_pipeline=summary_cfg,
        llms=[],
    )

    with pytest.raises(ValueError, match="LLM alias 'missing-llm' not found"):
        SummaryPipeline(config, base_path=tmp_path)


def test_summary_pipeline_skips_sources_when_fetcher_fails(tmp_path: Path) -> None:
    class FailingFetcher:
        def fetch(self, source: SummarySource) -> FetchResult:  # noqa: ARG002
            raise ContentUnavailableError("no content")

    config = _build_app_config(tmp_path)
    pipeline = SummaryPipeline(config, base_path=tmp_path, fetcher=FailingFetcher())

    artifacts = pipeline.run(
        [
            SummarySource(
                paper_id="2502.00002",
                title="Markdown Extraction Failures",
                abstract="This source cannot produce markdown",
            )
        ]
    )

    assert artifacts == []
