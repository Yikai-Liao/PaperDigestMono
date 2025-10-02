"""Upload abstractions for backup artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi
from loguru import logger

from papersys.config.backup import BackupDestinationConfig


class UploadError(RuntimeError):
    """Raised when uploading a backup bundle fails."""


class Uploader(ABC):
    """Abstract uploader definition."""

    @abstractmethod
    def upload(
        self,
        bundle_path: Path,
        *,
        dry_run: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Upload the given bundle and return a string representing the destination."""


class LocalUploader(Uploader):
    """Uploader that copies the artifact to a local directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def upload(
        self,
        bundle_path: Path,
        *,
        dry_run: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        destination = self.directory / bundle_path.name
        if dry_run:
            logger.info("[Dry Run] Would copy backup to {}", destination)
            return str(destination)

        self.directory.mkdir(parents=True, exist_ok=True)
        bundle_bytes = bundle_path.read_bytes()
        destination.write_bytes(bundle_bytes)
        logger.info("Backup copied to {}", destination)
        return str(destination)


class HuggingFaceDatasetUploader(Uploader):
    """Uploader that stores the artifact inside a Hugging Face dataset repository."""

    def __init__(self, repo_id: str, *, path_prefix: str = "", token: str | None = None) -> None:
        self.repo_id = repo_id
        self.path_prefix = path_prefix.strip("/")
        self.token = token
        self.api = HfApi()

    def upload(
        self,
        bundle_path: Path,
        *,
        dry_run: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        remote_path = bundle_path.name if not self.path_prefix else f"{self.path_prefix}/{bundle_path.name}"
        remote_uri = f"hf://{self.repo_id}/{remote_path}"

        if dry_run:
            logger.info("[Dry Run] Would upload backup to {}", remote_uri)
            return remote_uri

        try:
            self.api.upload_file(
                path_or_fileobj=bundle_path,
                repo_id=self.repo_id,
                path_in_repo=remote_path,
                repo_type="dataset",
                token=self.token,
            )
        except Exception as exc:  # pragma: no cover - rewrapped for clarity
            raise UploadError(f"Failed to upload backup to {remote_uri}: {exc}") from exc

        logger.info("Backup uploaded to {}", remote_uri)
        return remote_uri


def create_uploader(
    destination: BackupDestinationConfig,
    *,
    resolved_token: str | None = None,
) -> Uploader:
    """Instantiate the correct uploader based on configuration."""

    if destination.storage == "local":
        directory = destination.path
        if directory is None:  # Defensive, should already be validated
            raise ValueError("Local destination requires a path.")
        return LocalUploader(directory)

    token = resolved_token if resolved_token is not None else destination.token
    return HuggingFaceDatasetUploader(
        destination.repo_id or "", path_prefix=destination.repo_path, token=token
    )


__all__ = [
    "Uploader",
    "LocalUploader",
    "HuggingFaceDatasetUploader",
    "UploadError",
    "create_uploader",
]
