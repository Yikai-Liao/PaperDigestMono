"""Web console configuration models."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator

from papersys.config.base import BaseConfig


class WebAuthConfig(BaseConfig):
    """Settings for protecting the web console and related APIs."""

    enabled: bool = Field(
        False, description="Whether header token authentication is enforced.",
    )
    header_name: str = Field(
        "X-Console-Token",
        description="Header to read the authentication token from.",
        min_length=1,
    )
    token: str | None = Field(
        default=None, description="Shared secret token required when enabled.",
        min_length=1,
    )

    @field_validator("token")
    @classmethod
    def _strip_token(cls, token: str | None) -> str | None:
        if token is None:
            return None
        stripped = token.strip()
        return stripped if stripped else None

    @model_validator(mode="after")
    def _ensure_token_when_enabled(self) -> "WebAuthConfig":
        if self.enabled and not self.token:
            msg = "Authentication token must be provided when web auth is enabled."
            raise ValueError(msg)
        return self


class WebUIConfig(BaseConfig):
    """Top-level settings for the FastAPI web console."""

    enabled: bool = Field(True, description="Whether to expose the HTML console UI.")
    title: str = Field(
        "PaperDigest Console",
        description="Page title displayed on the console UI.",
        min_length=1,
    )
    auth: WebAuthConfig | None = Field(
        default=None,
        description="Authentication settings for the console and its APIs.",
    )


__all__ = ["WebAuthConfig", "WebUIConfig"]
