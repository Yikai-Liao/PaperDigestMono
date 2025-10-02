"""Configuration namespace for papersys."""

from __future__ import annotations

from .app import AppConfig
from .backup import BackupConfig, BackupDestinationConfig
from .base import BaseConfig, load_config
from .embedding import EmbeddingConfig, EmbeddingModelConfig
from .ingestion import IngestionConfig
from .llm import LLMConfig
from .recommend import (
    DataConfig,
    LogisticRegressionConfig,
    PredictConfig,
    RecommendPipelineConfig,
    TrainerConfig,
)
from .scheduler import SchedulerConfig, SchedulerJobConfig
from .summary import PdfConfig, SummaryPipelineConfig
from .utils import resolve_env_reference

__all__ = [
    "BaseConfig",
    "AppConfig",
    "load_config",
    "BackupConfig",
    "BackupDestinationConfig",
    "EmbeddingConfig",
    "EmbeddingModelConfig",
    "IngestionConfig",
    "LLMConfig",
    "DataConfig",
    "LogisticRegressionConfig",
    "PredictConfig",
    "RecommendPipelineConfig",
    "TrainerConfig",
    "SchedulerConfig",
    "SchedulerJobConfig",
    "PdfConfig",
    "SummaryPipelineConfig",
    "resolve_env_reference",
]
