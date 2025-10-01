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
from .summary import PdfConfig, SummaryPipelineConfig

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
    "PdfConfig",
    "SummaryPipelineConfig",
]
