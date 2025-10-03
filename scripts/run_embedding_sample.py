"""Run a constrained embedding flow for manual verification."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import typer
from loguru import logger

from papersys.config import AppConfig, load_config
from papersys.embedding import EmbeddingService

app = typer.Typer(add_completion=False)


def _resolve_base_path(config: AppConfig, config_path: Path) -> Path:
    base_path = config.data_root
    if base_path is None:
        return config_path.parent
    if base_path.is_absolute():
        return base_path
    return (config_path.parent / base_path).resolve()


def _select_model(config: AppConfig, alias: str | None) -> tuple[EmbeddingService, "EmbeddingModelConfig"]:
    if config.embedding is None or not config.embedding.enabled:
        raise typer.BadParameter("Embedding is disabled in the configuration")

    service = EmbeddingService(config.embedding)

    if alias:
        for model in config.embedding.models:
            if model.alias == alias:
                return service, model
        raise typer.BadParameter(f"Model alias '{alias}' not found in configuration")

    if not config.embedding.models:
        raise typer.BadParameter("No embedding models defined in configuration")
    logger.info("Using default model {}", config.embedding.models[0].alias)
    return service, config.embedding.models[0]


def _metadata_dir(base_path: Path, config: AppConfig) -> Path:
    if config.ingestion is None or not config.ingestion.output_dir:
        raise typer.BadParameter("Ingestion output_dir is required to locate metadata")
    raw = Path(config.ingestion.output_dir)
    return raw if raw.is_absolute() else base_path / raw


def _discover_metadata(metadata_dir: Path) -> list[Path]:
    flat = sorted(path for path in metadata_dir.glob("metadata-*.csv") if path.is_file())
    if flat:
        return flat

    nested: list[Path] = []
    if metadata_dir.exists():
        for child in sorted(metadata_dir.iterdir()):
            if child.is_dir():
                nested.extend(sorted(child.glob("*.csv")))
    return nested


def _log_plan(metadata_paths: Iterable[Path], model_alias: str, limit: int | None, backlog: bool) -> None:
    paths = list(metadata_paths)
    logger.info(
        "[Dry Run] Model={} backlog={} limit={} files={}",
        model_alias,
        backlog,
        limit,
        paths,
    )


@app.command()
def main(
    config_path: Path = typer.Option(
        Path(__file__).resolve().parents[1] / "config" / "example.toml",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the TOML configuration file",
    ),
    model: str | None = typer.Option(None, help="Model alias to use"),
    limit: int | None = typer.Option(None, min=1, help="Maximum number of rows per CSV"),
    backlog: bool = typer.Option(False, help="Process backlog entries instead of newest metadata"),
    dry_run: bool = typer.Option(False, help="Report actions without generating embeddings"),
) -> None:
    """Trigger the embedding service with a low record limit."""

    config_path = config_path.resolve()
    logger.info("Loading configuration from {}", config_path)
    config = load_config(AppConfig, config_path)

    base_path = _resolve_base_path(config, config_path)
    metadata_dir = _metadata_dir(base_path, config)
    service, model_config = _select_model(config, model)

    if not metadata_dir.exists():
        raise typer.BadParameter(f"Metadata directory not found: {metadata_dir}")

    if backlog:
        backlog_df = service.detect_backlog(metadata_dir, model_config)
        if backlog_df.is_empty():
            logger.info("No backlog items for model {}", model_config.alias)
            return
        metadata_paths = [Path(p) for p in backlog_df.select("origin").unique()["origin"].to_list()]
    else:
        candidates = _discover_metadata(metadata_dir)
        if not candidates:
            raise typer.BadParameter(f"No metadata CSV files found under {metadata_dir}")
        metadata_paths = [candidates[0]]

    if dry_run:
        _log_plan(metadata_paths, model_config.alias, limit, backlog)
        return

    total = 0
    for csv_path in metadata_paths:
        logger.info("Generating embeddings for {}", csv_path)
        count, output_path = service.generate_embeddings_for_csv(
            csv_path,
            model_config,
            limit=limit,
        )
        logger.info("Generated {} embeddings -> {}", count, output_path)
        total += count
        service.refresh_backlog(metadata_dir, model_config)

    logger.info("Sample embedding run complete; total embeddings generated: {}", total)


if __name__ == "__main__":
    app()

