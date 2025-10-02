"""Configuration namespace for papersys."""

from __future__ import annotations

from .app import AppConfig
from .backup import BackupConfig, BackupDestinationConfig
from .base import BaseConfig, load_config
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

__all__ = [
    "BaseConfig",
    "AppConfig",
    "load_config",
    "BackupConfig",
    "BackupDestinationConfig",
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
]
