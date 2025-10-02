from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from papersys.backup import BackupService
from papersys.config import AppConfig
from papersys.config.backup import BackupConfig, BackupDestinationConfig


class _FailingUploader:
    def upload(self, *args, **kwargs):  # type: ignore[override]
        raise RuntimeError("simulated upload failure")


def test_create_backup_bundle(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "include.txt").write_text("keep", encoding="utf-8")
    (source_dir / "skip.log").write_text("ignore", encoding="utf-8")

    backup_cfg = BackupConfig(
        enabled=True,
        name="test-backup",
        sources=[source_dir],
        exclude=["*.log"],
        staging_dir=tmp_path / "staging",
        destination=BackupDestinationConfig(storage="local", path=tmp_path / "dest"),
    )
    app_cfg = AppConfig(backup=backup_cfg)

    service = BackupService(app_cfg, dry_run=True)
    bundle = service.create_bundle()

    assert bundle.path.exists()

    with tarfile.open(bundle.path, "r:gz") as tar:
        members = tar.getnames()
        assert f"{source_dir.name}/include.txt" in members
        assert all("skip.log" not in name for name in members)

        manifest_member = tar.extractfile("MANIFEST.json")
        assert manifest_member is not None
        manifest = json.loads(manifest_member.read().decode("utf-8"))

    assert manifest["stats"]["files"] == 1
    assert manifest["entries"][0]["arcname"] == f"{source_dir.name}/include.txt"


def test_backup_failure_cleans_staging(tmp_path: Path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("data", encoding="utf-8")

    staging_dir = tmp_path / "staging"
    backup_cfg = BackupConfig(
        enabled=True,
        name="fail-backup",
        sources=[source_dir],
        staging_dir=staging_dir,
        destination=BackupDestinationConfig(storage="local", path=tmp_path / "dest"),
    )
    app_cfg = AppConfig(backup=backup_cfg)

    service = BackupService(
        app_cfg,
        dry_run=False,
        uploader_factory=lambda *args, **kwargs: _FailingUploader(),
    )

    with pytest.raises(RuntimeError):
        service.run()

    bundle_files = list(staging_dir.glob("*.tar.gz"))
    assert not bundle_files, "Staging artifacts should be removed after failure"
