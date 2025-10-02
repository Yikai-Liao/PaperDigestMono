"""Application-level configuration models."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from papersys.config.backup import BackupConfig
from papersys.config.base import BaseConfig
from papersys.config.embedding import EmbeddingConfig
from papersys.config.ingestion import IngestionConfig
from papersys.config.llm import LLMConfig
from papersys.config.recommend import RecommendPipelineConfig
from papersys.config.scheduler import SchedulerConfig
from papersys.config.summary import SummaryPipelineConfig


class AppConfig(BaseConfig):
    """Top-level runtime configuration for the entire application."""

    # Legacy fields for backward compatibility
    data_root: Path | None = Field(None, description="Root data directory (deprecated, use pipeline configs)")
    scheduler_enabled: bool = Field(True, description="Whether to enable scheduler service")
    embedding_models: list[str] = Field(default_factory=list, description="Legacy embedding model list")
    logging_level: str = Field("INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # New pipeline configurations
    ingestion: IngestionConfig | None = Field(None, description="Metadata ingestion configuration")
    embedding: EmbeddingConfig | None = Field(None, description="Embedding generation configuration")
    recommend_pipeline: RecommendPipelineConfig | None = None
    summary_pipeline: SummaryPipelineConfig | None = None
    scheduler: SchedulerConfig | None = Field(None, description="Scheduler configuration")
    backup: BackupConfig | None = Field(None, description="Backup configuration")
    llms: list[LLMConfig] = Field(default_factory=list, description="Available LLM configurations")


__all__ = ["AppConfig"]
