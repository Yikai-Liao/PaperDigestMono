"""Service for ingesting arXiv metadata and saving to CSV."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import polars as pl
from loguru import logger

from papersys.config.ingestion import IngestionConfig
from papersys.ingestion.client import ArxivOAIClient, ArxivRecord


class IngestionService:
    """Service for fetching and saving arXiv metadata."""

    def __init__(self, config: IngestionConfig):
        self.config = config
        self.client = ArxivOAIClient(
            base_url=config.oai_base_url,
            metadata_prefix=config.metadata_prefix,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
        )
        self.output_dir = Path(config.output_dir)
        self.curated_dir = Path(config.curated_dir)

    def fetch_and_save(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        limit: int | None = None,
    ) -> tuple[int, int]:
        """
        Fetch records from arXiv and save to CSV.

        Args:
            from_date: Start date in YYYY-MM-DD format (defaults to config.start_date)
            until_date: End date in YYYY-MM-DD format (defaults to config.end_date)
            limit: Maximum number of records to fetch (for testing)

        Returns:
            Tuple of (total_fetched, total_saved)
        """
        from_date = from_date or self.config.start_date
        until_date = until_date or self.config.end_date

        logger.info(
            "Starting ingestion: from={}, until={}, categories={}",
            from_date,
            until_date,
            self.config.categories,
        )

        total_fetched = 0
        total_saved = 0
        batch_buffer: list[dict] = []

        # Fetch all records and filter by category
        try:
            for record in self.client.list_records(
                from_date=from_date,
                until_date=until_date,
                set_spec=None,  # Don't use set filtering; filter client-side instead
            ):
                total_fetched += 1

                # Filter by primary category
                if record.primary_category not in self.config.categories:
                    continue

                batch_buffer.append(self._record_to_dict(record))

                # Save batch when buffer is full
                if len(batch_buffer) >= self.config.batch_size:
                    self._save_batch(batch_buffer)
                    total_saved += len(batch_buffer)
                    batch_buffer.clear()
                    logger.debug("Saved batch; total saved: {}", total_saved)

                # Check limit for testing
                if limit and total_saved >= limit:
                    logger.info("Reached save limit of {} records", limit)
                    break

        except Exception as exc:
            logger.error("Failed to fetch records: {}", exc)

        # Save remaining records
        if batch_buffer:
            self._save_batch(batch_buffer)
            total_saved += len(batch_buffer)

        logger.info(
            "Ingestion complete: fetched={}, saved={}",
            total_fetched,
            total_saved,
        )
        return total_fetched, total_saved

    def _record_to_dict(self, record: ArxivRecord) -> dict:
        """Convert ArxivRecord to dictionary for CSV serialization."""
        return {
            "paper_id": record.paper_id,
            "title": record.title,
            "abstract": record.abstract,
            "categories": "|".join(record.categories),  # Pipe-separated
            "primary_category": record.primary_category,
            "authors": "|".join(record.authors),  # Pipe-separated
            "published_at": record.published_at,
            "updated_at": record.updated_at,
            "doi": record.doi or "",
            "comment": record.comment or "",
            "journal_ref": record.journal_ref or "",
        }

    def _save_batch(self, batch: list[dict]) -> None:
        """Save batch of records to CSV file, organized by year."""
        if not batch:
            return

        # Group by publication year
        by_year: dict[int, list[dict]] = {}
        for item in batch:
            try:
                # Parse YYYY-MM-DD from published_at
                year = int(item["published_at"][:4])
            except (ValueError, IndexError):
                logger.warning("Invalid published_at format: {}", item.get("published_at"))
                continue

            by_year.setdefault(year, []).append(item)

        # Save each year's records
        for year, records in by_year.items():
            year_dir = self.output_dir / str(year)
            year_dir.mkdir(parents=True, exist_ok=True)

            csv_path = year_dir / f"arxiv_{year}.csv"
            file_exists = csv_path.exists()

            # Append to CSV
            with csv_path.open("a", newline="", encoding="utf-8") as f:
                fieldnames = [
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
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(records)

            logger.debug("Appended {} records to {}", len(records), csv_path)

    def deduplicate_csv_files(self) -> int:
        """
        Deduplicate CSV files by paper_id and keep the latest version.

        Returns:
            Total number of duplicates removed
        """
        total_removed = 0

        schema_overrides = {
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
        }

        for year_dir in self.output_dir.iterdir():
            if not year_dir.is_dir():
                continue

            for csv_path in year_dir.glob("*.csv"):
                try:
                    # Read with polars and explicit schema
                    df = pl.read_csv(csv_path, schema_overrides=schema_overrides)
                    original_count = len(df)

                    # Sort by updated_at descending, then deduplicate by paper_id
                    df = df.sort("updated_at", descending=True)
                    df = df.unique(subset=["paper_id"], keep="first")

                    removed = original_count - len(df)
                    if removed > 0:
                        # Write back
                        df.write_csv(csv_path)
                        logger.info("Deduplicated {}: removed {} duplicates", csv_path.name, removed)
                        total_removed += removed

                except Exception as exc:
                    logger.error("Failed to deduplicate {}: {}", csv_path, exc)

        return total_removed


__all__ = ["IngestionService"]
