from __future__ import annotations

from pathlib import Path

from papersys.backup.uploader import HuggingFaceDatasetUploader, LocalUploader


def test_local_uploader_dry_run(tmp_path: Path) -> None:
    dest_dir = tmp_path / "dest"
    bundle = tmp_path / "bundle.tar.gz"
    bundle.write_bytes(b"content")

    uploader = LocalUploader(dest_dir)
    result = uploader.upload(bundle, dry_run=True)

    assert result.endswith("bundle.tar.gz")
    assert not (dest_dir / "bundle.tar.gz").exists()


def test_hf_uploader_dry_run(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    bundle.write_bytes(b"content")

    uploader = HuggingFaceDatasetUploader("org/dataset", path_prefix="backups", token="dummy")

    called = False

    def _fail_upload(*args, **kwargs):  # pragma: no cover - should not be called
        nonlocal called
        called = True
        raise AssertionError("upload_file should not be invoked in dry run")

    monkeypatch.setattr(uploader.api, "upload_file", _fail_upload)

    remote_uri = uploader.upload(bundle, dry_run=True)

    assert remote_uri == "hf://org/dataset/backups/bundle.tar.gz"
    assert called is False
