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
    LogisticRegressionConfig,
    PredictConfig,
    RecommendPipelineConfig,
    PdfFetchConfig,
    TrainerConfig,
    DataConfig,
    SummaryLLMConfig,
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
    include_recommend: bool = False,
) -> AppConfig:
    """Construct an in-memory AppConfig tailored for CLI tests."""

    data_root = base_dir / "data"
    data_root.mkdir(parents=True, exist_ok=True)

    ingestion_cfg = None
    if include_ingestion:
        raw_dir = data_root / "metadata" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        ingestion_cfg = IngestionConfig(
            enabled=True,
            output_dir=str(raw_dir),
            start_date=None,
            end_date=None,
            batch_size=1000,
            max_retries=3,
            retry_delay=5.0,
            oai_base_url="http://export.arxiv.org/oai2",
            metadata_prefix="arXiv",
            categories=["cs.CL"],
            save_raw_responses=False,
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
            batch_size=32,
            max_length=512,
            device=None,
            precision="auto",
            backend="sentence_transformer",
            model_path=None,
        )
        embedding_models.append(embedding_model)
        embedding_cfg = EmbeddingConfig(
            enabled=True,
            output_dir=str(embed_dir),
            models=embedding_models,
            auto_fill_backlog=True,
            backlog_priority="recent_first",
            max_parallel_models=1,
            checkpoint_interval=1000,
            upload_to_hf=False,
            hf_repo_id=None,
            hf_token=None,
        )

    summary_cfg = None
    llms: list[LLMConfig] = []
    if include_summary:
        llm_config = LLMConfig(
            alias="summary-llm",
            name="mock-llm",
            base_url="http://localhost",
            api_key="dummy",
            temperature=0.0,
            top_p=1.0,
            num_workers=1,
            reasoning_effort=None,
        )
        llms.append(llm_config)
        summary_cfg = SummaryPipelineConfig(
            pdf=PdfFetchConfig(
                output_dir="summaries/pdfs",
                delay=0,
                max_retry=1,
                fetch_latex_source=False,
            ),
            llm=SummaryLLMConfig(
                model=llm_config.alias,
                language="en",
                enable_latex=False,
            ),
        )

    recommend_cfg = None
    if include_recommend:
        preference_dir = data_root / "preferences"
        metadata_dir = data_root / "metadata"
        embeddings_root = data_root / "embeddings"
        for directory in (preference_dir, metadata_dir, embeddings_root):
            directory.mkdir(parents=True, exist_ok=True)

        recommend_cfg = RecommendPipelineConfig(
            data=DataConfig(
                categories=["cs.AI"],
                embedding_columns=["test"],
                preference_dir=str(preference_dir.relative_to(data_root)),
                metadata_dir=str(metadata_dir.relative_to(data_root)),
                metadata_pattern="metadata-*.csv",
                embeddings_root=str(embeddings_root.relative_to(data_root)),
                background_start_year=2024,
                preference_start_year=2024,
            ),
            trainer=TrainerConfig(
                seed=42,
                bg_sample_rate=1.0,
                logistic_regression=LogisticRegressionConfig(C=1.0, max_iter=100),
            ),
            predict=PredictConfig(
                last_n_days=7,
                start_date="",
                end_date="",
                high_threshold=0.9,
                boundary_threshold=0.7,
                sample_rate=0.5,
                output_dir="recommendations",
                output_path="predictions.parquet",
                recommended_path="recommended.parquet",
                manifest_path="manifest.json",
            ),
        )

    return AppConfig(
        data_root=data_root,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        ingestion=ingestion_cfg,
        embedding=embedding_cfg,
        summary_pipeline=summary_cfg,
        llms=llms,
        recommend_pipeline=recommend_cfg,
        scheduler=None,
        backup=None,
    )


def patch_load_config(monkeypatch: MonkeyPatch, config: AppConfig) -> None:
    """Force the CLI to return the provided config instead of reading from disk."""

    def _fake_load_config(model: object, path: Path) -> AppConfig:
        if model is not AppConfig:
            raise AssertionError("Unexpected config model request")
        return config

    monkeypatch.setattr("papersys.cli.load_config", _fake_load_config)
