"""Run a constrained ingestion flow for manual verification."""

from __future__ import annotations

from pathlib import Path
import sys
import typer
from loguru import logger
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from papersys.config import AppConfig, load_config
from papersys.ingestion import IngestionService
from papersys.ingestion.service import _SCHEMA

app = typer.Typer(add_completion=True)


def _resolve_base_path(config: AppConfig, config_path: Path) -> Path:
    base_path = config.data_root
    if base_path is None:
        return config_path.parent
    if base_path.is_absolute():
        return base_path
    return (config_path.parent / base_path).resolve()


@app.command()
def main(
    config_path: Path = typer.Option(
        Path(__file__).resolve().parents[1] / "config" / "example.toml",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the TOML configuration file",
    ),
    limit: int | None = typer.Option(None, help="Maximum number of records to fetch/save (None for unlimited)"),
    from_date: str | None = typer.Option(None, help="Optional start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, help="Optional end date (YYYY-MM-DD)"),
    save: bool = typer.Option(False, help="Save fetched records to disk"),
    dry_run: bool = typer.Option(False, help="Log target paths without hitting the network"),
    deduplicate: bool = typer.Option(False, help="Run deduplication after ingestion"),
) -> None:
    """Trigger the ingestion service with optional record fetching and saving."""
    config_path = config_path.resolve()
    logger.info("Loading configuration from {}", config_path)
    config: AppConfig = load_config(AppConfig, config_path)


    if config.ingestion is None or not config.ingestion.enabled:
        logger.error("Ingestion is disabled in the provided configuration")
        raise typer.Exit(1)

    ingestion_cfg = config.ingestion
    logger.info("Loaded configuration: {}", ingestion_cfg.model_dump())
    base_path = _resolve_base_path(config, config_path)
    logger.info("Resolved data root to {}", base_path)

    service = IngestionService(ingestion_cfg, base_path=base_path)

    if dry_run:
        logger.info(
            "[Dry Run] Would fetch from {} to {} (limit={} save={})",
            from_date or ingestion_cfg.start_date,
            to_date or ingestion_cfg.end_date,
            limit,
            save,
        )
        return

    # Fetch records
    records = service.fetch_records(
        from_date=from_date,
        until_date=to_date,
        limit=limit,
    )
    logger.info("Fetched {} records", len(records))

    # Convert to DataFrame for inspection
    if records:
        rows = [service._record_to_row(record) for record in records]
        df_before_dedup = pl.DataFrame(rows, schema=_SCHEMA)
        logger.info("DataFrame before deduplication:\n{}", df_before_dedup)
    else:
        logger.info("No records fetched")
        return

    if save:
        # Save records (this includes deduplication)
        saved = service.save_records(records)
        logger.info("Saved {} records to disk", saved)

        # Show deduplicated DataFrame
        if service.latest_path.exists():
            df_after_dedup = pl.read_csv(service.latest_path, schema_overrides=_SCHEMA)
            logger.info("DataFrame after deduplication:\n{}", df_after_dedup)
    else:
        logger.info("Skipping save (use --save to enable)")

    if deduplicate and save:
        removed = service.deduplicate_csv_files()
        logger.info("Deduplicated {} additional records", removed)


if __name__ == "__main__":
    app()

