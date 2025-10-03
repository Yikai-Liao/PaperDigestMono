"""Tests for the arXiv ingestion service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import polars as pl
import pytest

from papersys.config.ingestion import IngestionConfig
from papersys.ingestion.client import ArxivRecord
from papersys.ingestion.service import IngestionService


SCHEMA_OVERRIDES = {
    "paper_id": pl.String,
    "title": pl.String,
    "abstract": pl.String,
    "categories": pl.String,
    "primary_category": pl.String,
    "authors": pl.String,
    "published_at": pl.String,
    "updated_at": pl.String,
    "doi": pl.String,
    "comment": pl.String,
    "journal_ref": pl.String,
    "license": pl.String,
    "source": pl.String,
}


@pytest.fixture
def test_config() -> IngestionConfig:
    """Create ingestion configuration for tests."""
    return IngestionConfig(
        enabled=True,
        output_dir="metadata",
        curated_dir="curated",
        start_date="2023-01-01",
        end_date="2023-01-31",
        batch_size=2,
        max_retries=1,
        retry_delay=0.1,
        oai_base_url="http://export.arxiv.org/oai2",
        metadata_prefix="arXiv",
        categories=["cs.AI", "cs.CL"],
        save_raw_responses=False,
    )


@pytest.fixture
def test_service(test_config: IngestionConfig, tmp_path: Path) -> IngestionService:
    """Instantiate the ingestion service with a temporary base path."""
    return IngestionService(test_config, base_path=tmp_path)


def test_record_to_row(test_service: IngestionService) -> None:
    """The row serialisation should normalise delimiters and optional fields."""
    record = ArxivRecord(
        paper_id="2301.00001",
        title="Test Paper",
        abstract="Test abstract",
        categories=["cs.AI", "cs.CL"],
        primary_category="cs.AI",
        authors=["John Doe", "Jane Smith"],
        published_at="2023-01-01",
        updated_at="2023-01-02",
        doi="10.1234/test",
        comment="5 pages",
        journal_ref="Test Journal",
        license="CC-BY-4.0",
    )

    row = test_service._record_to_row(record)

    assert row["categories"] == "cs.AI;cs.CL"
    assert row["authors"] == "John Doe;Jane Smith"
    assert row["license"] == "CC-BY-4.0"
    assert row["source"] == "papersys.ingestion.oai"


def test_flush_rows_creates_year_files(test_service: IngestionService) -> None:
    """Flushing rows should create yearly files and the latest snapshot."""
    record1 = ArxivRecord(
        paper_id="2301.00001",
        title="Paper 1",
        abstract="Abstract 1",
        categories=["cs.AI"],
        primary_category="cs.AI",
        authors=["John Doe"],
        published_at="2023-01-01",
        updated_at="2023-01-01",
    )
    record2 = ArxivRecord(
        paper_id="2301.00002",
        title="Paper 2",
        abstract="Abstract 2",
        categories=["cs.CL"],
        primary_category="cs.CL",
        authors=["Jane Smith"],
        published_at="2023-01-02",
        updated_at="2023-01-02",
    )

    rows = [test_service._record_to_row(record1), test_service._record_to_row(record2)]
    test_service._flush_rows(rows)

    year_path = test_service.output_dir / "metadata-2023.csv"
    latest_path = test_service.output_dir / "latest.csv"

    assert year_path.exists()
    assert latest_path.exists()

    df_year = pl.read_csv(year_path, schema_overrides=SCHEMA_OVERRIDES)
    df_latest = pl.read_csv(latest_path, schema_overrides=SCHEMA_OVERRIDES)

    assert df_year.height == 2
    assert df_latest.height == 2
    assert "cs.AI;" not in df_year["categories"].to_list()[0]  # Already normalised


def test_flush_rows_updates_existing_records(test_service: IngestionService) -> None:
    """Later updates should win when paper_id matches."""
    initial = ArxivRecord(
        paper_id="2301.00001",
        title="Initial",
        abstract="Old",
        categories=["cs.AI"],
        primary_category="cs.AI",
        authors=["John Doe"],
        published_at="2023-01-01",
        updated_at="2023-01-01",
        comment="old",
    )
    updated = ArxivRecord(
        paper_id="2301.00001",
        title="Updated",
        abstract="New",
        categories=["cs.AI"],
        primary_category="cs.AI",
        authors=["John Doe"],
        published_at="2023-01-01",
        updated_at="2023-01-05",
        comment="new",
    )

    test_service._flush_rows([test_service._record_to_row(initial)])
    test_service._flush_rows([test_service._record_to_row(updated)])

    year_path = test_service.output_dir / "metadata-2023.csv"
    df_year = pl.read_csv(year_path, schema_overrides=SCHEMA_OVERRIDES)

    assert df_year.height == 1
    assert df_year["title"].to_list() == ["Updated"]
    assert df_year["comment"].to_list() == ["new"]


def test_deduplicate_csv_files(test_service: IngestionService) -> None:
    """Explicit deduplication should remove duplicate identifiers."""
    year_path = test_service.output_dir / "metadata-2023.csv"
    frame = pl.DataFrame(
        {
            "paper_id": ["1", "1", "2"],
            "title": ["v1", "v2", "paper2"],
            "abstract": ["a1", "a2", "a3"],
            "categories": ["cs.AI", "cs.AI", "cs.CL"],
            "primary_category": ["cs.AI", "cs.AI", "cs.CL"],
            "authors": ["John", "John", "Jane"],
            "published_at": ["2023-01-01", "2023-01-01", "2023-01-02"],
            "updated_at": ["2023-01-01", "2023-01-02", "2023-01-02"],
            "doi": ["", "", ""],
            "comment": ["old", "new", ""],
            "journal_ref": ["", "", ""],
            "license": ["", "", ""],
            "source": ["legacy", "legacy", "legacy"],
        }
    )
    year_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(year_path)

    removed = test_service.deduplicate_csv_files()
    assert removed == 1

    df_year = pl.read_csv(year_path, schema_overrides=SCHEMA_OVERRIDES)
    assert df_year.height == 2
    assert df_year.sort("paper_id")["comment"].to_list() == ["new", ""]


@patch("papersys.ingestion.service.ArxivOAIClient.list_records")
def test_fetch_and_save_with_limit(
    mock_list_records: Mock,
    test_service: IngestionService,
) -> None:
    """The fetch loop should respect the record save limit."""
    mock_list_records.return_value = [
        ArxivRecord(
            paper_id="2301.00001",
            title="Paper 1",
            abstract="Abstract 1",
            categories=["cs.AI"],
            primary_category="cs.AI",
            authors=["John Doe"],
            published_at="2023-01-01",
            updated_at="2023-01-01",
        ),
        ArxivRecord(
            paper_id="2301.00002",
            title="Paper 2",
            abstract="Abstract 2",
            categories=["cs.CL"],
            primary_category="cs.CL",
            authors=["Jane Smith"],
            published_at="2023-01-02",
            updated_at="2023-01-02",
        ),
        ArxivRecord(
            paper_id="2301.00003",
            title="Paper 3",
            abstract="Abstract 3",
            categories=["cs.AI"],
            primary_category="cs.AI",
            authors=["Bob Johnson"],
            published_at="2023-01-03",
            updated_at="2023-01-03",
        ),
    ]

    fetched, saved = test_service.fetch_and_save(limit=2)

    assert fetched == 2
    assert saved == 2

    year_path = test_service.output_dir / "metadata-2023.csv"
    df_year = pl.read_csv(year_path, schema_overrides=SCHEMA_OVERRIDES)
    assert df_year.height == 2
    assert set(df_year["paper_id"].to_list()) == {"2301.00001", "2301.00002"}

