"""Run a constrained ingestion flow for manual verification."""

from __future__ import annotations

from pathlib import Path

import typer
from loguru import logger

from papersys.config import AppConfig, load_config
from papersys.ingestion import IngestionService

app = typer.Typer(add_completion=False)


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
    limit: int = typer.Option(5, min=1, help="Maximum number of records to save"),
    from_date: str | None = typer.Option(None, help="Optional start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, help="Optional end date (YYYY-MM-DD)"),
    dry_run: bool = typer.Option(False, help="Log target paths without hitting the network"),
    deduplicate: bool = typer.Option(False, help="Run deduplication after ingestion"),
) -> None:
    """Trigger the ingestion service with a low record limit."""
    config_path = config_path.resolve()
    logger.info("Loading configuration from {}", config_path)
    config = load_config(AppConfig, config_path)

    if config.ingestion is None or not config.ingestion.enabled:
        logger.error("Ingestion is disabled in the provided configuration")
        raise typer.Exit(1)

    ingestion_cfg = config.ingestion
    base_path = _resolve_base_path(config, config_path)
    logger.info("Resolved data root to {}", base_path)

    service = IngestionService(ingestion_cfg, base_path=base_path)

    if dry_run:
        logger.info(
            "[Dry Run] Would save yearly metadata under {} (limit={} from={} to={})",
            service.output_dir,
            limit,
            from_date or ingestion_cfg.start_date,
            to_date or ingestion_cfg.end_date,
        )
        return

    fetched, saved = service.fetch_and_save(
        from_date=from_date,
        until_date=to_date,
        limit=limit,
    )
    logger.info("Fetch complete: fetched={} saved={}", fetched, saved)

    if deduplicate:
        removed = service.deduplicate_csv_files()
        logger.info("Deduplicated {} records", removed)


if __name__ == "__main__":
    app()

