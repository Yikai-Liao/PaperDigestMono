"""Run the summary pipeline against recommendation outputs with minimal setup."""

from __future__ import annotations

from pathlib import Path

import typer
from loguru import logger

from papersys.config import AppConfig, load_config
from papersys.summary import SummaryPipeline

app = typer.Typer(add_completion=False)


def _resolve_base_path(config: AppConfig, config_path: Path) -> Path:
    base = config.data_root
    if base is None:
        return config_path.parent
    if isinstance(base, Path) and base.is_absolute():
        return base
    if isinstance(base, Path):
        return (config_path.parent / base).resolve()
    return (config_path.parent / Path(str(base))).resolve()


def _discover_latest_recommendation(base_path: Path) -> Path | None:
    root = (base_path / "recommendations").resolve()
    if not root.exists():
        return None
    candidate_dirs = sorted((entry for entry in root.iterdir() if entry.is_dir()), reverse=True)
    for directory in candidate_dirs:
        for filename in ("recommended.parquet", "recommended.jsonl", "predictions.parquet"):
            candidate = directory / filename
            if candidate.exists():
                return candidate
    return None


@app.command()
def main(
    config_path: Path = typer.Option(
        Path(__file__).resolve().parents[1] / "config" / "example.toml",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the TOML configuration file",
    ),
    input: Path | None = typer.Option(
        None,
        "--input",
        help="Path to recommended output (recommended.parquet/jsonl). Defaults to latest run",
    ),
    limit: int | None = typer.Option(None, min=1, help="Maximum number of papers to summarise"),
    dry_run: bool = typer.Option(False, help="Inspect pipeline directories without generating summaries"),
) -> None:
    """Execute the summary pipeline with stub fetchers/LLMs by default."""

    config_path = config_path.resolve()
    logger.info("Loading configuration from {}", config_path)
    config = load_config(AppConfig, config_path)

    if config.summary_pipeline is None:
        raise typer.BadParameter("Summary pipeline is not enabled in the configuration")

    base_path = _resolve_base_path(config, config_path)
    try:
        pipeline = SummaryPipeline(config, base_path=base_path)
    except (ValueError, EnvironmentError) as exc:
        raise typer.BadParameter(f"Failed to initialise summary pipeline: {exc}") from exc
    pipeline.describe_sources()

    if dry_run:
        pipeline.run([], dry_run=True)
        logger.info("[Dry Run] Summary pipeline was not executed.")
        return

    resolved_input = input
    if resolved_input is not None and not resolved_input.is_absolute():
        resolved_input = (base_path / resolved_input).resolve()

    if resolved_input is None:
        resolved_input = _discover_latest_recommendation(base_path)
        if resolved_input is None:
            raise typer.BadParameter(
                "Cannot locate recommendation outputs; provide --input explicitly."
            )

    sources = pipeline.load_sources_from_recommendations(resolved_input, limit=limit)
    if not sources:
        logger.warning("No candidates found in {}; nothing to summarise", resolved_input)
        return

    report = pipeline.run_and_save(sources, limit=limit)

    logger.info("Summary JSONL updated at {}", report.jsonl_path)
    logger.info("Summary manifest written to {}", report.manifest_path)
    logger.info("Markdown outputs available in {}", report.markdown_dir)


if __name__ == "__main__":
    app()
