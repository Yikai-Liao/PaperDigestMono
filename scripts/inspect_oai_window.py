"""Utility script to probe the arXiv OAI-PMH endpoint over a given date range.

This script streams records without persisting them, making it suitable for
manual verification of pagination behaviour and potential server-side limits.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from papersys.ingestion.client import ArxivOAIClient  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    from_date: str = typer.Option(..., help="Start date in YYYY-MM-DD format"),
    until_date: str = typer.Option(..., help="End date in YYYY-MM-DD format"),
    max_records: int | None = typer.Option(
        None,
        help="Optional hard cap on streamed records; set to avoid very long runs",
    ),
    log_interval: int = typer.Option(
        5000,
        min=1,
        help="Log a progress message every N records",
    ),
) -> None:
    """Stream records and report basic statistics for the requested window."""
    client = ArxivOAIClient()

    start = time.perf_counter()
    total_streamed = 0

    logger.info(
        "Starting OAI probe: from={} until={} max_records={} log_interval={}",
        from_date,
        until_date,
        max_records,
        log_interval,
    )

    first_record_date = None
    last_record_date = None

    try:
        for record in client.list_records(from_date=from_date, until_date=until_date):
            total_streamed += 1
            
            # Track date range of received records
            if first_record_date is None:
                first_record_date = record.updated_at or record.published_at
            last_record_date = record.updated_at or record.published_at
            
            if log_interval and total_streamed % log_interval == 0:
                elapsed = time.perf_counter() - start
                logger.info(
                    "Progress: streamed {} records in {:.1f}s (avg {:.1f} rec/s) | last_date={}",
                    total_streamed,
                    elapsed,
                    total_streamed / elapsed if elapsed else 0.0,
                    last_record_date,
                )

            if max_records is not None and total_streamed >= max_records:
                logger.warning(
                    "Reached max_records={} before server exhausted window",
                    max_records,
                )
                break
    except KeyboardInterrupt:  # pragma: no cover - manual abort
        logger.warning("Interrupted by user after {} records", total_streamed)
    finally:
        elapsed = time.perf_counter() - start
        logger.info(
            "Probe complete: streamed={} duration={:.1f}s avg_rate={:.1f} rec/s",
            total_streamed,
            elapsed,
            total_streamed / elapsed if elapsed else 0.0,
        )
        logger.info(
            "Date range: first_record={} last_record={}",
            first_record_date,
            last_record_date,
        )


if __name__ == "__main__":
    app()
