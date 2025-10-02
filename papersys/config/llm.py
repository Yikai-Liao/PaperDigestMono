"""LLM configuration models."""

from __future__ import annotations

from pydantic import Field

from papersys.config.base import BaseConfig
from papersys.config.utils import resolve_env_reference


class LLMConfig(BaseConfig):
    """Configuration for a single language model endpoint."""

    alias: str = Field(..., description="Model alias for reference")
    name: str = Field(..., description="Model name/identifier for API calls")
    base_url: str = Field(..., description="API base URL")
    api_key: str = Field(..., description="API key, can use 'env:VAR_NAME' format")
    temperature: float = Field(0.1, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(0.8, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    num_workers: int = Field(1, ge=1, description="Concurrent worker count")
    reasoning_effort: str | None = Field(None, description="Reasoning effort level for certain models")

    @property
    def api_key_secret(self) -> str:
        """Return the resolved API key, expanding any ``env:VAR`` references."""

        resolved = resolve_env_reference(self.api_key)
        assert resolved is not None  # guarded by resolve_env_reference
        return resolved


__all__ = ["LLMConfig"]
