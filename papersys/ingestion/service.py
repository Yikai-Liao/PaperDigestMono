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
        self.curated_dir = self._resolve_output_dir(Path(config.curated_dir), base_path)
        self.curated_dir.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.output_dir / "latest.csv"

    def fetch_and_save(
        self,
        from_date: str | None = None,
        until_date: str | None = None,
        limit: int | None = None,
    ) -> tuple[int, int]:
        """
        Fetch records from arXiv and save them to yearly CSV files under `output_dir`.

        Records are grouped by publication year and written to `metadata-YYYY.csv` files.
        A consolidated `latest.csv` snapshot is refreshed on each successful flush.

        Args:
            from_date: Start date in YYYY-MM-DD format (defaults to config.start_date).
            until_date: End date in YYYY-MM-DD format (defaults to config.end_date).
            limit: Maximum number of records to persist (testing convenience).

        Returns:
            Tuple of (total_fetched, total_saved) counts.
        """
        from_date = from_date or self.config.start_date
        until_date = until_date or self.config.end_date

        categories_to_fetch = self.config.categories or [None]
        
        logger.info(
            "Starting ingestion: from={}, until={}, categories={}, limit={}",
            from_date,
            until_date,
            self.config.categories,
            limit,
        )

        total_fetched = 0
        total_saved = 0
        buffer: list[dict[str, str]] = []

        # Fetch records for each category separately to use server-side filtering
        for category in categories_to_fetch:
            if limit is not None and total_saved >= limit:
                logger.info("Reached save limit before processing all categories")
                break
                
            if category:
                logger.info("Fetching category: {}", category)
            
            try:
                for record in self.client.list_records(
                    from_date=from_date,
                    until_date=until_date,
                    set_spec=category,
                ):
                    total_fetched += 1

                    total_saved, stop = self._handle_record_during_fetch(
                        record=record,
                        buffer=buffer,
                        total_saved=total_saved,
                        limit=limit,
                    )
                    if stop:
                        break

            except Exception as exc:
                logger.error("Failed to fetch records for category {}: {}", category, exc)

        # Flush any remaining rows in buffer, respecting limit
        total_saved = self._flush_buffer_with_limit(buffer, total_saved, limit)

        logger.info(
            "Ingestion complete: fetched={}, saved={}",
            total_fetched,
            total_saved,
        )
        return total_fetched, total_saved

    def _handle_record_during_fetch(
        self,
        record: ArxivRecord,
        buffer: list[dict[str, str]],
        total_saved: int,
        limit: int | None,
    ) -> tuple[int, bool]:
        """Process a single fetched record: append to buffer and flush if needed.

        Returns the updated total_saved count and a stop flag indicating the
        fetch loop should terminate (True when the save limit has been reached).
        """
        buffer.append(self._record_to_row(record))

        # If a limit is set, check remaining capacity and flush partial buffer when needed
        if limit is not None:
            remaining = max(limit - total_saved, 0)
            if remaining == 0:
                logger.info("Reached save limit of {} records", limit)
                return total_saved, True
            if len(buffer) >= remaining:
                rows_to_save = buffer[:remaining]
                self._flush_rows(rows_to_save)
                total_saved += len(rows_to_save)
                buffer.clear()
                logger.info("Reached save limit of {} records", limit)
                return total_saved, True

        # Flush by batch size when buffer is full
        if len(buffer) >= self.config.batch_size:
            self._flush_rows(buffer)
            total_saved += len(buffer)
            buffer.clear()

        return total_saved, False

    def _flush_buffer_with_limit(
        self,
        buffer: list[dict[str, str]],
        total_saved: int,
        limit: int | None,
    ) -> int:
        """Flush any remaining rows in buffer, respecting an optional limit.

        Returns the updated total_saved count.
        """
        if not buffer or (limit is not None and total_saved >= limit):
            return total_saved

        if limit is not None:
            remaining = max(limit - total_saved, 0)
            if remaining <= 0:
                buffer.clear()
                return total_saved
            rows_to_save = buffer[:remaining]
            self._flush_rows(rows_to_save)
            total_saved += len(rows_to_save)
            buffer.clear()
            return total_saved

        # No limit: flush everything
        self._flush_rows(buffer)
        total_saved += len(buffer)
        buffer.clear()
        return total_saved

    def deduplicate_csv_files(self) -> int:
        """Deduplicate yearly CSV files and refresh `latest.csv`."""

        total_removed = 0
        for year_file in sorted(self.output_dir.glob("metadata-*.csv")):
            try:
                frame = pl.read_csv(year_file, schema_overrides=_SCHEMA)
                frame = self._normalise_dataframe(frame)
                original_count = frame.height
                frame = self._deduplicate_dataframe(frame)
                removed = original_count - frame.height
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

        if total_removed > 0:
            self._update_latest_view()

        return total_removed

    def _flush_rows(self, rows: Iterable[dict[str, str]]) -> None:
        grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            year = self._extract_year(row.get("published_at", ""))
            if year is None:
                logger.warning("Skipping record with invalid published_at: {}", row)
                continue
            grouped[year].append(row)

        for year, year_rows in grouped.items():
            self._write_year_file(year, year_rows)

        if grouped:
            self._update_latest_view()

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

        combined = self._deduplicate_dataframe(combined)
        combined.select(_COLUMN_ORDER).write_csv(year_path)
        logger.debug("Wrote {} records to {}", len(rows), year_path)

    def _update_latest_view(self) -> None:
        year_files = sorted(self.output_dir.glob("metadata-*.csv"))
        if not year_files:
            return

        lazy_frames = [
            pl.scan_csv(year_file, schema_overrides=_SCHEMA)
            for year_file in year_files
        ]
        combined = pl.concat(lazy_frames, how="vertical_relaxed").collect()
        combined = self._deduplicate_dataframe(combined)
        combined.select(_COLUMN_ORDER).write_csv(self.latest_path)
        logger.debug("Refreshed latest.csv with {} records", combined.height)

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
