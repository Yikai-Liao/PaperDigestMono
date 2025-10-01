"""Application-level configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field, ConfigDict

from .base import BaseConfig


class AppConfig(BaseConfig):
    """Top-level runtime configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_root: Path
    scheduler_enabled: bool = True
    embedding_models: List[str] = Field(default_factory=list)
    logging_level: str = "INFO"


__all__ = ["AppConfig"]
