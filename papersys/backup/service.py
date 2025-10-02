"""Backup service responsible for packaging and uploading artifacts."""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from loguru import logger

from papersys.config import AppConfig, BackupConfig

from .uploader import Uploader, create_uploader


@dataclass(frozen=True)
class BackupResult:
    """Outcome of a backup run."""

    bundle_path: Path
    remote_uri: str | None
    file_count: int
    total_bytes: int
    manifest: dict[str, Any]


@dataclass(frozen=True)
class BackupBundle:
    """A packaged backup artifact prior to upload."""

    path: Path
    manifest: dict[str, Any]
    ephemeral_root: Path | None


class BackupService:
    """Service that prepares and uploads backup archives."""

    def __init__(
        self,
        config: AppConfig,
        *,
        dry_run: bool = False,
        uploader_factory: Callable[..., Uploader] | None = None,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self._uploader_factory = uploader_factory or create_uploader

    def create_bundle(self) -> BackupBundle:
        """Create a backup bundle without uploading it."""
        backup_cfg = self._require_config()
        bundle = self._build_bundle(backup_cfg)
        logger.info(
            "Created backup bundle %s with %d files (%.2f KiB)",
            bundle.path.name,
            bundle.manifest["stats"]["files"],
            bundle.manifest["stats"]["bytes"] / 1024,
        )
        return bundle

    def run(self) -> BackupResult | None:
        """Execute the full backup flow (bundle + upload)."""
        backup_cfg = self.config.backup
        if not backup_cfg or not backup_cfg.enabled:
            logger.info("Backup pipeline is disabled; skipping execution.")
            return None

        bundle = self._build_bundle(backup_cfg)
        uploader = self._make_uploader(backup_cfg)

        remote_uri: str | None = None
        try:
            remote_uri = uploader.upload(
                bundle.path,
                dry_run=self.dry_run,
                metadata=bundle.manifest,
            )
        except Exception:
            logger.exception("Backup upload failed; removing staging artifact %s", bundle.path)
            self._cleanup_bundle(bundle)
            raise

        logger.info(
            "Backup run finished: %s files (%.2f KiB) -> %s",
            bundle.manifest["stats"]["files"],
            bundle.manifest["stats"]["bytes"] / 1024,
            remote_uri,
        )

        if not self.dry_run:
            self._post_upload_cleanup(bundle, backup_cfg)
        return BackupResult(
            bundle_path=bundle.path,
            remote_uri=remote_uri,
            file_count=bundle.manifest["stats"]["files"],
            total_bytes=bundle.manifest["stats"]["bytes"],
            manifest=bundle.manifest,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _require_config(self) -> BackupConfig:
        backup_cfg = self.config.backup
        if not backup_cfg:
            raise ValueError("Backup configuration is not defined in AppConfig.")
        if not backup_cfg.sources:
            raise ValueError("Backup configuration must define at least one source path.")
        return backup_cfg

    def _build_bundle(self, backup_cfg: BackupConfig) -> BackupBundle:
        timestamp = datetime.now(timezone.utc)
        slug = timestamp.strftime("%Y%m%dT%H%M%SZ")

        if backup_cfg.staging_dir:
            staging_root = backup_cfg.staging_dir.expanduser()
            staging_root.mkdir(parents=True, exist_ok=True)
            ephemeral_root: Path | None = None
        else:
            tmp_dir = tempfile.mkdtemp(prefix="papersys-backup-")
            staging_root = Path(tmp_dir)
            ephemeral_root = staging_root

        bundle_path = staging_root / f"{backup_cfg.name}-{slug}.tar.gz"
        manifest_entries: list[dict] = []
        total_bytes = 0
        file_count = 0

        with tarfile.open(bundle_path, "w:gz") as tar:
            for source in backup_cfg.sources:
                source_path = Path(source).expanduser()
                if not source_path.exists():
                    logger.warning("Backup source %s does not exist; skipping.", source_path)
                    continue

                for file_path, arcname in self._iter_source_files(source_path):
                    if self._is_excluded(arcname, backup_cfg.exclude):
                        continue

                    tar.add(file_path, arcname=str(arcname))
                    size = file_path.stat().st_size
                    manifest_entries.append(
                        {
                            "source": str(file_path),
                            "arcname": str(arcname),
                            "size": size,
                        }
                    )
                    total_bytes += size
                    file_count += 1

            manifest: dict[str, Any] = {
                "name": backup_cfg.name,
                "created_at": timestamp.isoformat().replace("+00:00", "Z"),
                "sources": [str(Path(src)) for src in backup_cfg.sources],
                "exclude": list(backup_cfg.exclude),
                "stats": {"files": file_count, "bytes": total_bytes},
                "entries": manifest_entries,
            }
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            info = tarfile.TarInfo("MANIFEST.json")
            info.size = len(manifest_bytes)
            info.mtime = int(timestamp.timestamp())
            tar.addfile(info, io.BytesIO(manifest_bytes))

        return BackupBundle(path=bundle_path, manifest=manifest, ephemeral_root=ephemeral_root)

    def _iter_source_files(self, source: Path) -> Iterable[tuple[Path, Path]]:
        if source.is_file():
            yield source, Path(source.name)
            return

        for file_path in sorted(p for p in source.rglob("*") if p.is_file()):
            arcname = Path(source.name) / file_path.relative_to(source)
            yield file_path, arcname

    def _is_excluded(self, arcname: Path, patterns: Sequence[str]) -> bool:
        if not patterns:
            return False
        candidate = arcname.as_posix()
        for pattern in patterns:
            if fnmatch(candidate, pattern) or fnmatch(arcname.name, pattern):
                return True
        return False

    def _make_uploader(self, backup_cfg: BackupConfig) -> Uploader:
        token = self._resolve_token(backup_cfg.destination.token)
        return self._uploader_factory(backup_cfg.destination, resolved_token=token)

    def _resolve_token(self, token: str | None) -> str | None:
        if not token:
            return None
        if token.startswith("env:"):
            var_name = token.split(":", 1)[1]
            resolved = os.getenv(var_name)
            if not resolved:
                raise EnvironmentError(f"Environment variable '{var_name}' for backup token is not set.")
            return resolved
        return token

    def _post_upload_cleanup(self, bundle: BackupBundle, backup_cfg: BackupConfig) -> None:
        bundle.path.unlink(missing_ok=True)
        if bundle.ephemeral_root and bundle.ephemeral_root.exists():
            shutil.rmtree(bundle.ephemeral_root, ignore_errors=True)

        if backup_cfg.destination.storage == "local":
            self._enforce_retention(backup_cfg)

    def _cleanup_bundle(self, bundle: BackupBundle) -> None:
        bundle.path.unlink(missing_ok=True)
        if bundle.ephemeral_root and bundle.ephemeral_root.exists():
            shutil.rmtree(bundle.ephemeral_root, ignore_errors=True)

    def _enforce_retention(self, backup_cfg: BackupConfig) -> None:
        directory = backup_cfg.destination.path
        if not directory or not directory.exists():
            return

        archives = sorted(
            (p for p in directory.iterdir() if p.is_file() and p.suffixes[-2:] == [".tar", ".gz"]),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in archives[backup_cfg.retention :]:
            logger.info("Removing expired local backup %s", old_file)
            old_file.unlink(missing_ok=True)


__all__ = ["BackupService", "BackupResult", "BackupBundle"]
