"""Backup configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from papersys.config.base import BaseConfig


class BackupDestinationConfig(BaseConfig):
    """Configuration describing where a backup artifact should be stored."""

    storage: Literal["local", "huggingface"] = Field(
        "local",
        description="Storage backend for the backup artifact",
    )
    path: Path | None = Field(
        Path("./backups"),
        description="Destination directory when using local storage",
    )
    repo_id: str | None = Field(
        None,
        description="Hugging Face dataset repository identifier (e.g. org/dataset)",
    )
    repo_path: str = Field(
        "backups",
        description="Directory within the repository to store the archive",
    )
    token: str | None = Field(
        None,
        description="Access token or 'env:VAR_NAME' reference for remote storage",
    )

    @model_validator(mode="after")
    def _validate_destination(self) -> "BackupDestinationConfig":
        if self.storage == "local":
            if self.path is None:
                raise ValueError("Local backup destination requires 'path'.")
        elif self.storage == "huggingface":
            if not self.repo_id:
                raise ValueError("Hugging Face destination requires 'repo_id'.")
        return self


class BackupConfig(BaseConfig):
    """Top-level backup configuration."""

    enabled: bool = Field(False, description="Whether automated backup is enabled")
    name: str = Field("daily-backup", description="Friendly identifier for the backup bundle")
    sources: list[Path] = Field(
        default_factory=list,
        description="List of file or directory paths to include in the backup",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Glob patterns (relative to sources) to exclude from the archive",
    )
    staging_dir: Path | None = Field(
        None,
        description="Optional directory to store temporary backup bundles before upload",
    )
    destination: BackupDestinationConfig = Field(
        default_factory=BackupDestinationConfig,
        description="Destination configuration for uploaded backups",
    )
    retention: int = Field(
        7,
        ge=1,
        description="Retention window (number of most recent backups) for local storage",
    )

    @model_validator(mode="after")
    def _validate_sources(self) -> "BackupConfig":
        if self.enabled and not self.sources:
            raise ValueError("At least one source must be configured when backup is enabled.")
        return self


__all__ = ["BackupConfig", "BackupDestinationConfig"]
