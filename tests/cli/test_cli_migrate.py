from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from papersys.cli import main

from .utils import logger_to_stderr, make_app_config, patch_load_config


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    config_file = tmp_path / "config.toml"
    config_file.write_text("placeholder = true", encoding="utf-8")
    return config_file


def _write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "id,preference\n"
    lines = [header] + [f"{paper_id},{value}\n" for paper_id, value in rows]
    path.write_text("".join(lines), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cli_migrate_legacy_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
    capsys: Any,
) -> None:
    config = make_app_config(tmp_path, include_ingestion=False, include_embedding=False, include_summary=False)
    patch_load_config(monkeypatch, config)

    reference_root = tmp_path / "reference"
    paper_digest = reference_root / "PaperDigest"
    paper_digest_action = reference_root / "PaperDigestAction"

    _write_csv(paper_digest / "preference" / "2024-01.csv", [("paper-001", "like")])
    _write_json(
        paper_digest / "raw" / "2024" / "paper-001.json",
        {
            "id": "paper-001",
            "summary": "Legacy summary",
            "summary_time": "2024-01-01T00:00:00Z",
        },
    )
    _write_json(
        paper_digest_action / "summarized" / "paper-002.json",
        {
            "id": "paper-002",
            "summary": "Action summary",
            "summary_time": "2024-01-02T00:00:00Z",
        },
    )

    output_root = tmp_path / "output"

    with logger_to_stderr():
        exit_code = main(
            [
                "--config",
                str(config_path),
                "migrate",
                "legacy",
                "--reference-root",
                str(reference_root),
                "--output-root",
                str(output_root),
                "--dry-run",
                "--hf-dataset",
                "",
            ]
        )

    assert exit_code == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["preferences"]["input_files"] == 1
    assert report["summaries"]["records"] == 2
    validation_targets = {entry["target"]: entry["status"] for entry in report["validation"]}
    assert validation_targets["preferences-2024"] == "ok"
    assert validation_targets["summaries-2024-01"] == "ok"


def test_cli_migrate_legacy_strict_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config_path: Path,
) -> None:
    config = make_app_config(tmp_path, include_ingestion=False, include_embedding=False, include_summary=False)
    patch_load_config(monkeypatch, config)

    reference_root = tmp_path / "reference"
    paper_digest = reference_root / "PaperDigest"

    _write_json(
        paper_digest / "raw" / "2024" / "paper-001.json",
        {
            "id": "paper-001",
            "summary_time": "2024-01-01T00:00:00Z",
        },
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "migrate",
            "legacy",
            "--reference-root",
            str(reference_root),
            "--output-root",
            str(tmp_path / "output"),
            "--dry-run",
            "--hf-dataset",
            "",
        ]
    )

    assert exit_code == 1
