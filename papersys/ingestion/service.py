"""Service for ingesting arXiv metadata and writing canonical CSV outputs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import polars as pl
from loguru import logger

from papersys.config.ingestion import IngestionConfig
from papersys.ingestion.client import ArxivOAIClient, ArxivRecord


_COLUMN_ORDER: tuple[str, ...] = (
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
    "license",
    "source",
)

_SCHEMA: dict[str, pl.DataType] = {column: pl.String for column in _COLUMN_ORDER}
_SOURCE_TAG = "papersys.ingestion.oai"


class IngestionService:
    """Service for fetching arXiv metadata and saving to canonical CSV files."""

    def __init__(self, config: IngestionConfig, base_path: Path | None = None):
        self.config = config
        self.base_path = base_path
        self.client = ArxivOAIClient(
            base_url=config.oai_base_url,
            metadata_prefix=config.metadata_prefix,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
        )
        self.output_dir = self._resolve_output_dir(Path(config.output_dir), base_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_records(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        limit: int | None = None,
    ) -> list[ArxivRecord]:
        """
        Fetch records from arXiv without persisting them.

        Args:
            from_date: Start date in YYYY-MM-DD format (defaults to config.start_date).
            until_date: End date in YYYY-MM-DD format (defaults to config.end_date).
            limit: Maximum number of records to fetch (optional).

        Returns:
            List of ArxivRecord objects with paper metadata.
        """
        from_date = from_date or self.config.start_date
        until_date = until_date or self.config.end_date
        categories_to_fetch = self.config.categories or [None]

        logger.info(
            "Fetching records: from={}, until={}, categories={}, limit={}",
            from_date,
            until_date,
            self.config.categories,
            limit,
        )

        all_records: list[ArxivRecord] = []

        for category in categories_to_fetch:
            if limit is not None and len(all_records) >= limit:
                logger.info("Reached fetch limit before processing all categories")
                break

            if category:
                logger.info("Fetching category: {}", category)

            try:
                for record in self.client.list_records(
                    from_date=from_date,
                    until_date=until_date,
                    set_spec=category,
                ):
                    all_records.append(record)

                    if limit is not None and len(all_records) >= limit:
                        logger.info("Reached fetch limit of {} records", limit)
                        break

            except Exception as exc:
                logger.error("Failed to fetch records for category {}: {}", category, exc)

        logger.info(
            "Fetch complete: collected={} records",
            len(all_records),
        )
        return all_records

    def save_records(
        self,
        records: list[ArxivRecord],
    ) -> int:
        """
        Save records to yearly CSV files.

        Args:
            records: List of ArxivRecord objects to save.

        Returns:
            Number of records successfully saved.
        """
        if not records:
            logger.warning("No records to save")
            return 0

        logger.info("Saving {} records to disk", len(records))

        # Convert to rows and group by year
        grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
        for record in records:
            row = self._record_to_row(record)
            year = self._extract_year(row.get("published_at", ""))
            if year is None:
                logger.warning("Skipping record with invalid published_at: {}", record.paper_id)
                continue
            grouped[year].append(row)

        for year, year_rows in grouped.items():
            self._write_year_file(year, year_rows)

        total_saved = sum(len(rows) for rows in grouped.values())
        logger.info("Save complete: saved={} records", total_saved)
        return total_saved

    def fetch_and_save(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        limit: int | None = None,
    ) -> tuple[int, int]:
        """
        Fetch records from arXiv and save them to yearly CSV files under `output_dir`.

        Records are grouped by publication year and written to `metadata-YYYY.csv` files.

        Args:
            from_date: Start date in YYYY-MM-DD format (defaults to config.start_date).
            until_date: End date in YYYY-MM-DD format (defaults to config.end_date).
            limit: Maximum number of records to persist (testing convenience).

        Returns:
            Tuple of (total_fetched, total_saved) counts.
        """
        from_date = from_date or self.config.start_date
        until_date = until_date or self.config.end_date

        logger.info(
            "Starting ingestion: from={}, until={}, categories={}, limit={}",
            from_date,
            until_date,
            self.config.categories,
            limit,
        )

        records = self.fetch_records(
            from_date=from_date,
            until_date=until_date,
            limit=limit,
        )

        total_saved = self.save_records(records)

        logger.info(
            "Ingestion complete: fetched={}, saved={}",
            len(records),
            total_saved,
        )
        return len(records), total_saved

    def deduplicate_csv_files(self) -> int:
        """Deduplicate yearly CSV files."""

        total_removed = 0
        for year_file in sorted(self.output_dir.glob("metadata-*.csv")):
            try:
                frame = pl.read_csv(year_file, schema_overrides=_SCHEMA)
                frame = self._normalise_dataframe(frame)
                original_count = frame.height
                frame = self._deduplicate_dataframe(frame)
                removed = original_count - frame.height
                logger.debug(
                    "Deduplicated {}: {} records before, {} records after, removed {} duplicates",
                    year_file.name,
                    original_count,
                    frame.height,
                    removed,
                )
                if removed > 0:
                    frame.select(_COLUMN_ORDER).write_csv(year_file)
                    total_removed += removed
                    logger.info(
                        "Deduplicated {}: removed {} duplicates",
                        year_file.name,
                        removed,
                    )
            except Exception as exc:
                logger.error("Failed to deduplicate {}: {}", year_file, exc)

        return total_removed

    def _write_year_file(self, year: int, rows: list[dict[str, str]]) -> None:
        if not rows:
            return

        year_path = self.output_dir / f"metadata-{year}.csv"
        new_frame = self._build_frame(rows)

        if year_path.exists():
            existing_frame = pl.read_csv(year_path, schema_overrides=_SCHEMA)
            existing_frame = self._normalise_dataframe(existing_frame)
            combined = pl.concat([existing_frame, new_frame], how="vertical_relaxed")
        else:
            combined = new_frame

        logger.debug("Year {}: {} records before deduplication", year, combined.height)
        combined = self._deduplicate_dataframe(combined)
        logger.debug("Year {}: {} records after deduplication", year, combined.height)

        combined.select(_COLUMN_ORDER).write_csv(year_path)
        logger.debug("Wrote {} records to {}", len(rows), year_path)

    def _record_to_row(self, record: ArxivRecord) -> dict[str, str]:
        return {
            "paper_id": record.paper_id,
            "title": record.title,
            "abstract": record.abstract,
            "categories": ";".join(record.categories),
            "primary_category": record.primary_category,
            "authors": ";".join(record.authors),
            "published_at": record.published_at or "",
            "updated_at": record.updated_at or "",
            "doi": record.doi or "",
            "comment": record.comment or "",
            "journal_ref": record.journal_ref or "",
            "license": record.license or "",
            "source": _SOURCE_TAG,
        }

    def _build_frame(self, rows: list[dict[str, str]]) -> pl.DataFrame:
        frame = pl.DataFrame(rows, schema=_SCHEMA)
        return self._normalise_dataframe(frame)

    def _normalise_dataframe(self, frame: pl.DataFrame) -> pl.DataFrame:
        # Ensure all expected columns exist and are typed as strings.
        missing = [column for column in _COLUMN_ORDER if column not in frame.columns]
        if missing:
            frame = frame.with_columns([pl.lit("").alias(column) for column in missing])

        for column in _COLUMN_ORDER:
            frame = frame.with_columns(pl.col(column).cast(pl.String, strict=False))

        return frame.select(_COLUMN_ORDER)

    def _deduplicate_dataframe(self, frame: pl.DataFrame) -> pl.DataFrame:
        sorted_frame = frame.sort(
            ["paper_id", "updated_at"],
            descending=[False, True],
        )
        deduped = (
            sorted_frame
            .unique(subset=["paper_id"], keep="first")
            .sort(["published_at", "paper_id"], descending=[True, False])
        )
        return deduped

    def _extract_year(self, value: str) -> int | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).year
        except ValueError:
            try:
                return int(value[:4])
            except (ValueError, TypeError):
                return None

    def _resolve_output_dir(self, raw_path: Path, base_path: Path | None) -> Path:
        if raw_path.is_absolute():
            return raw_path
        if base_path is not None:
            return base_path / raw_path
        return raw_path


__all__ = ["IngestionService"]
