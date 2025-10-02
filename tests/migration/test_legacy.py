from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import polars as pl

from papersys.migration.legacy import LegacyMigrator, MigrationConfig


def _write_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    header = "id,preference\n"
    lines = [header] + [f"{paper_id},{value}\n" for paper_id, value in rows]
    path.write_text("".join(lines), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, payloads: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in payloads:
            fh.write(json.dumps(item) + "\n")


def _base_config(tmp_path: Path, dry_run: bool) -> MigrationConfig:
    reference_root = tmp_path / "reference"
    paper_digest = reference_root / "PaperDigest"
    paper_digest_action = reference_root / "PaperDigestAction"
    paper_digest.mkdir(parents=True, exist_ok=True)
    paper_digest_action.mkdir(parents=True, exist_ok=True)

    output_root = tmp_path / "output"

    return MigrationConfig(
        output_root=output_root,
        reference_roots=(paper_digest, paper_digest_action),
        hf_dataset=None,
        years=None,
        models=None,
        dry_run=dry_run,
        force=True,
        cache_dir=None,
    )


def test_migrator_merges_preferences_and_summaries(tmp_path):
    config = _base_config(tmp_path, dry_run=False)
    paper_digest, paper_digest_action = config.reference_roots

    preference_dir = paper_digest / "preference"
    preference_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        preference_dir / "2024-01.csv",
        [
            ("paper-001", "like"),
            ("paper-002", "skip"),
            ("", "ignored"),
        ],
    )
    _write_csv(
        preference_dir / "2024-02.csv",
        [
            ("paper-001", "love"),
            ("paper-003", "star"),
        ],
    )

    summary_dir = paper_digest / "raw"
    _write_json(
        summary_dir / "2024" / "paper-001.json",
        {
            "id": "paper-001",
            "summary": "Legacy summary",
            "summary_time": "2024-02-03T08:00:00Z",
        },
    )

    action_summary_dir = paper_digest_action / "summarized"
    _write_jsonl(
        action_summary_dir / "paper-003.jsonl",
        [
            {
                "id": "paper-003",
                "summary": "Action summary",
                "summary_time": "2024-02-10T09:00:00Z",
            }
        ],
    )

    migrator = LegacyMigrator(config)
    report = migrator.run()
    preferences = cast(dict[str, Any], report["preferences"])

    preference_output = config.output_root / "preferences"
    events_path = preference_output / "events-2024.csv"
    assert events_path.exists()

    events_df = pl.read_csv(events_path)
    assert events_df.height == 4
    assert set(events_df.columns) == {
        "paper_id",
        "preference",
        "recorded_at",
    }
    assert set(events_df["paper_id"].to_list()) == {"paper-001", "paper-002", "paper-003"}
    assert events_df.filter(pl.col("paper_id") == "paper-001").shape[0] == 2
    assert (
        events_df.filter(pl.col("recorded_at") == "2024-01-01T00:00:00+00:00").shape[0]
        == 2
    )
    assert (
        events_df.filter(pl.col("recorded_at") == "2024-02-01T00:00:00+00:00").shape[0]
        == 2
    )
    assert preferences["rows"] == 4
    assert preferences["unique_ids"] == 3
    assert preferences["skipped_rows"] == 1

    summary_output = config.output_root / "summaries" / "2024-02.jsonl"
    assert summary_output.exists()
    payloads = [json.loads(line) for line in summary_output.read_text(encoding="utf-8").splitlines() if line]
    assert {item["id"] for item in payloads} == {"paper-001", "paper-003"}
    first_line = summary_output.read_text(encoding="utf-8").splitlines()[0]
    ordered_pairs = json.loads(first_line, object_pairs_hook=list)
    assert [key for key, _ in ordered_pairs] == [
        "id",
        "summary",
        "summary_time",
        "migrated_at",
        "source",
        "source_file",
    ]

    report_path = config.output_root / "migration-report.json"
    assert report_path.exists()
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_data["preferences"]["unique_ids"] == 3
    assert report_data["summaries"]["records"] == 2


def test_dry_run_skips_writes(tmp_path):
    config = _base_config(tmp_path, dry_run=True)
    paper_digest, _ = config.reference_roots

    preference_dir = paper_digest / "preference"
    preference_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(preference_dir / "2024-01.csv", [("paper-001", "like")])

    migrator = LegacyMigrator(config)
    report = migrator.run()
    preferences = cast(dict[str, Any], report["preferences"])

    assert preferences["rows"] == 1
    assert not (config.output_root / "preferences").exists()
    assert not (config.output_root / "migration-report.json").exists()
