"""Run the recommendation pipeline with minimal parameters for manual verification."""

from __future__ import annotations

from pathlib import Path

import typer
from loguru import logger

from papersys.config import AppConfig, load_config
from papersys.recommend import RecommendationPipeline

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


@app.command()
def main(
    config_path: Path = typer.Option(
        Path(__file__).resolve().parents[1] / "config" / "example.toml",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the TOML configuration file",
    ),
    force_all: bool = typer.Option(
        False,
        "--force-all",
        help="Force include all scored candidates in the recommendation output",
    ),
    output_dir: Path | None = typer.Option(
        None,
        help="Override output directory for recommendation artifacts",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Inspect resolved data sources without running training/prediction",
    ),
) -> None:
    """Execute the recommendation pipeline with the current configuration."""

    config_path = config_path.resolve()
    logger.info("Loading configuration from {}", config_path)
    config = load_config(AppConfig, config_path)

    if config.recommend_pipeline is None:
        raise typer.BadParameter("Recommendation pipeline is not enabled in the configuration")

    base_path = _resolve_base_path(config, config_path)
    pipeline = RecommendationPipeline(config, base_path=base_path)
    pipeline.describe_sources()

    if dry_run:
        logger.info("[Dry Run] Recommendation pipeline was not executed.")
        return

    resolved_output = output_dir
    if resolved_output is not None and not resolved_output.is_absolute():
        resolved_output = (base_path / resolved_output).resolve()

    report = pipeline.run_and_save(
        force_include_all=force_all,
        output_dir=resolved_output,
    )

    logger.info("Recommendation predictions written to {}", report.predictions_path)
    logger.info("Recommendation shortlist written to {}", report.recommended_path)
    logger.info("Recommendation manifest written to {}", report.manifest_path)


if __name__ == "__main__":
    app()
