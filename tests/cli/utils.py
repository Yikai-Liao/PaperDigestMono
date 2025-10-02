"""Shared helpers for CLI tests."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

from loguru import logger
from pytest import MonkeyPatch

from papersys.config import (
    AppConfig,
    EmbeddingConfig,
    EmbeddingModelConfig,
    IngestionConfig,
    LLMConfig,
    PdfConfig,
    SummaryPipelineConfig,
)


@contextmanager
def logger_to_stderr(level: str = "INFO"):
    """Temporarily route Loguru output to stderr for assertion."""

    handler_id = logger.add(sys.stderr, level=level)
    try:
        yield
    finally:
        logger.remove(handler_id)


def make_app_config(
    base_dir: Path,
    *,
    include_ingestion: bool = True,
    include_embedding: bool = True,
    include_summary: bool = True,
) -> AppConfig:
    """Construct an in-memory AppConfig tailored for CLI tests."""

    data_root = base_dir / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    ingestion_cfg = None
    if include_ingestion:
        raw_dir = data_root / "metadata" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        curated_dir = data_root / "metadata" / "curated"
        curated_dir.mkdir(parents=True, exist_ok=True)
        ingestion_cfg = IngestionConfig(
            enabled=True,
            output_dir=str(raw_dir),
            curated_dir=str(curated_dir),
            categories=["cs.CL"],
        )

    embedding_cfg = None
    embedding_models: list[EmbeddingModelConfig] = []
    if include_embedding:
        embed_dir = data_root / "embeddings"
        embed_dir.mkdir(parents=True, exist_ok=True)
        embedding_model = EmbeddingModelConfig(
            alias="test",
            name="sentence-transformer/test",
            dimension=384,
        )
        embedding_models.append(embedding_model)
        embedding_cfg = EmbeddingConfig(
            enabled=True,
            output_dir=str(embed_dir),
            models=embedding_models,
        )

    summary_cfg = None
    llms: list[LLMConfig] = []
    if include_summary:
        llm_config = LLMConfig(
            alias="summary-llm",
            name="mock-llm",
            base_url="http://localhost",
            api_key="dummy",
        )
        llms.append(llm_config)
        summary_cfg = SummaryPipelineConfig(
            pdf=PdfConfig(
                output_dir="summaries/pdfs",
                model=llm_config.alias,
            )
        )

    return AppConfig(
        data_root=data_root,
        ingestion=ingestion_cfg,
        embedding=embedding_cfg,
        summary_pipeline=summary_cfg,
        llms=llms,
    )


def patch_load_config(monkeypatch: MonkeyPatch, config: AppConfig) -> None:
    """Force the CLI to return the provided config instead of reading from disk."""

    def _fake_load_config(model: object, path: Path) -> AppConfig:
        if model is not AppConfig:
            raise AssertionError("Unexpected config model request")
        return config

    monkeypatch.setattr("papersys.cli.load_config", _fake_load_config)
