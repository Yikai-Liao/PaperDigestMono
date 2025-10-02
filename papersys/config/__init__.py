"""Configuration namespace for papersys."""

from __future__ import annotations

from .app import AppConfig
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
from .web import WebAuthConfig, WebUIConfig

__all__ = [
    "BaseConfig",
    "AppConfig",
    "load_config",
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
    "WebAuthConfig",
    "WebUIConfig",
]
