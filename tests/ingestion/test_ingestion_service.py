"""Tests for ingestion service."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import Mock, patch

import polars as pl
import pytest

from papersys.config.ingestion import IngestionConfig
from papersys.ingestion.client import ArxivRecord
from papersys.ingestion.service import IngestionService


@pytest.fixture
def test_config(tmp_path: Path) -> IngestionConfig:
    """Create test configuration."""
    return IngestionConfig(
        enabled=True,
        output_dir=str(tmp_path / "metadata" / "raw" / "arxiv"),
        curated_dir=str(tmp_path / "metadata" / "curated"),
        start_date="2023-01-01",
        end_date="2023-01-31",
        batch_size=2,
        max_retries=3,
        retry_delay=0.1,
        oai_base_url="http://export.arxiv.org/oai2",
        metadata_prefix="arXiv",
        categories=["cs.AI", "cs.CL"],
        save_raw_responses=False,
    )


@pytest.fixture
def test_service(test_config: IngestionConfig) -> IngestionService:
    """Create test ingestion service."""
    return IngestionService(test_config)


def test_record_to_dict(test_service: IngestionService) -> None:
    """Test converting ArxivRecord to dictionary."""
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
    )

    result = test_service._record_to_dict(record)

    assert result["paper_id"] == "2301.00001"
    assert result["title"] == "Test Paper"
    assert result["abstract"] == "Test abstract"
    assert result["categories"] == "cs.AI|cs.CL"
    assert result["primary_category"] == "cs.AI"
    assert result["authors"] == "John Doe|Jane Smith"
    assert result["published_at"] == "2023-01-01"
    assert result["updated_at"] == "2023-01-02"
    assert result["doi"] == "10.1234/test"
    assert result["comment"] == "5 pages"
    assert result["journal_ref"] == "Test Journal"


def test_save_batch(test_service: IngestionService, tmp_path: Path) -> None:
    """Test saving batch of records to CSV."""
    batch = [
        {
            "paper_id": "2301.00001",
            "title": "Paper 1",
            "abstract": "Abstract 1",
            "categories": "cs.AI",
            "primary_category": "cs.AI",
            "authors": "John Doe",
            "published_at": "2023-01-01",
            "updated_at": "2023-01-01",
            "doi": "",
            "comment": "",
            "journal_ref": "",
        },
        {
            "paper_id": "2301.00002",
            "title": "Paper 2",
            "abstract": "Abstract 2",
            "categories": "cs.CL",
            "primary_category": "cs.CL",
            "authors": "Jane Smith",
            "published_at": "2023-01-02",
            "updated_at": "2023-01-02",
            "doi": "",
            "comment": "",
            "journal_ref": "",
        },
    ]

    test_service._save_batch(batch)

    # Check that files were created
    csv_2023 = Path(test_service.output_dir) / "2023" / "arxiv_2023.csv"
    assert csv_2023.exists()

    # Read and verify content (with explicit schema to preserve string types)
    df = pl.read_csv(csv_2023, schema_overrides={"paper_id": pl.String})
    assert len(df) == 2
    assert df["paper_id"].to_list() == ["2301.00001", "2301.00002"]
    assert df["title"].to_list() == ["Paper 1", "Paper 2"]


def test_save_batch_appends(test_service: IngestionService, tmp_path: Path) -> None:
    """Test that save_batch appends to existing CSV."""
    batch1 = [
        {
            "paper_id": "2301.00001",
            "title": "Paper 1",
            "abstract": "Abstract 1",
            "categories": "cs.AI",
            "primary_category": "cs.AI",
            "authors": "John Doe",
            "published_at": "2023-01-01",
            "updated_at": "2023-01-01",
            "doi": "",
            "comment": "",
            "journal_ref": "",
        }
    ]

    batch2 = [
        {
            "paper_id": "2301.00002",
            "title": "Paper 2",
            "abstract": "Abstract 2",
            "categories": "cs.CL",
            "primary_category": "cs.CL",
            "authors": "Jane Smith",
            "published_at": "2023-01-02",
            "updated_at": "2023-01-02",
            "doi": "",
            "comment": "",
            "journal_ref": "",
        }
    ]

    test_service._save_batch(batch1)
    test_service._save_batch(batch2)

    # Check that records were appended
    csv_2023 = Path(test_service.output_dir) / "2023" / "arxiv_2023.csv"
    df = pl.read_csv(csv_2023, schema_overrides={"paper_id": pl.String})
    assert len(df) == 2
    assert df["paper_id"].to_list() == ["2301.00001", "2301.00002"]


def test_deduplicate_csv_files(test_service: IngestionService, tmp_path: Path) -> None:
    """Test deduplicating CSV files."""
    # Create CSV with duplicates
    output_dir = Path(test_service.output_dir)
    year_dir = output_dir / "2023"
    year_dir.mkdir(parents=True, exist_ok=True)
    csv_path = year_dir / "arxiv_2023.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "paper_id",
                "title",
                "abstract",
                "categories",
                "primary_category",
                "authors",
                "published_at",
                "updated_at",
                "doi",
                "comment",
                "journal_ref",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "paper_id": "2301.00001",
                    "title": "Paper 1 v1",
                    "abstract": "Old abstract",
                    "categories": "cs.AI",
                    "primary_category": "cs.AI",
                    "authors": "John Doe",
                    "published_at": "2023-01-01",
                    "updated_at": "2023-01-01",
                    "doi": "",
                    "comment": "",
                    "journal_ref": "",
                },
                {
                    "paper_id": "2301.00001",
                    "title": "Paper 1 v2",
                    "abstract": "New abstract",
                    "categories": "cs.AI",
                    "primary_category": "cs.AI",
                    "authors": "John Doe",
                    "published_at": "2023-01-01",
                    "updated_at": "2023-01-02",  # Later version
                    "doi": "",
                    "comment": "",
                    "journal_ref": "",
                },
                {
                    "paper_id": "2301.00002",
                    "title": "Paper 2",
                    "abstract": "Abstract 2",
                    "categories": "cs.CL",
                    "primary_category": "cs.CL",
                    "authors": "Jane Smith",
                    "published_at": "2023-01-02",
                    "updated_at": "2023-01-02",
                    "doi": "",
                    "comment": "",
                    "journal_ref": "",
                },
            ]
        )

    removed = test_service.deduplicate_csv_files()

    assert removed == 1

    # Verify deduplicated content
    df = pl.read_csv(csv_path, schema_overrides={"paper_id": pl.String})
    assert len(df) == 2
    assert df.filter(pl.col("paper_id") == "2301.00001")["title"].to_list() == ["Paper 1 v2"]


@patch("papersys.ingestion.service.ArxivOAIClient.list_records")
def test_fetch_and_save_with_limit(
    mock_list_records: Mock,
    test_service: IngestionService,
    tmp_path: Path,
) -> None:
    """Test fetch_and_save with limit."""
    # Mock records
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

    # Verify CSV was created
    csv_2023 = Path(test_service.output_dir) / "2023" / "arxiv_2023.csv"
    assert csv_2023.exists()
