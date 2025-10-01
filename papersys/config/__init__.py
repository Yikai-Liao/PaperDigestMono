"""Configuration namespace for papersys."""

from __future__ import annotations

from .app import AppConfig
from .base import BaseConfig, load_config

__all__ = ["BaseConfig", "AppConfig", "load_config"]
