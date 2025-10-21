"""Regression tests for the legacy migration helpers."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from papersys.migration.legacy import LegacyMigrator, MigrationConfig


def _make_config(output_root: Path) -> MigrationConfig:
    reference_a = output_root / "ref-a"
    reference_b = output_root / "ref-b"
    reference_a.mkdir(parents=True, exist_ok=True)
    reference_b.mkdir(parents=True, exist_ok=True)
    return MigrationConfig(
        output_root=output_root,
        reference_roots=(reference_a, reference_b),
        hf_dataset=None,
        years=None,
        models=None,
        dry_run=False,
        force=True,
    )


def test_migration_no_longer_writes_backlog(tmp_path: Path) -> None:
    output_root = tmp_path / "data"
    output_root.mkdir()
    migrator = LegacyMigrator(_make_config(output_root))

    frame = pl.DataFrame(
        {
            "id": ["paper-001", "paper-002"],
            "title": ["Example 1", "Example 2"],
            "abstract": ["Abstract 1", "Abstract 2"],
            "categories": [["cs.AI"], ["cs.AI"]],
            "authors": [["Alice"], ["Bob"]],
            "created": ["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"],
            "updated": ["2025-01-03T00:00:00Z", "2025-01-04T00:00:00Z"],
            "jasper_v1": [[0.1, 0.2], [0.3, 0.4]],
        }
    )

    metadata_df, embeddings = migrator._prepare_year_artifacts(2025, frame)
    migrator._write_year_artifacts(2025, (metadata_df, embeddings))
    migrator._finalize_metadata()
    migrator._finalize_embeddings()

    model_dir = output_root / "embeddings" / "jasper_v1"
    assert (model_dir / "2025.parquet").exists()
    assert (model_dir / "manifest.json").exists()
    assert not any(model_dir.glob("backlog*.parquet"))
