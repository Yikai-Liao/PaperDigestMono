"""Command line interface for the papersys toolkit."""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from .config import AppConfig, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Papersys orchestration helpers")
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to the TOML configuration file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load configuration and report subsystem availability",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = args.config.resolve()
    logger.info("Loading configuration from {}", config_path)
    config = load_config(AppConfig, config_path)

    if args.dry_run:
        _report_system_status(config)
        return 0

    logger.warning("No active commands were provided. Use --dry-run for status checks.")
    return 0


def _report_system_status(config: AppConfig) -> None:
    """Print detailed status of configuration and subsystems."""
    logger.info("=== General Configuration ===")
    logger.info("Data root: {}", config.data_root)
    logger.info("Scheduler enabled: {}", config.scheduler_enabled)
    logger.info("Logging level: {}", config.logging_level)

    if config.embedding_models:
        logger.info("Embedding models ({}): {}", len(config.embedding_models), ", ".join(config.embedding_models))
    else:
        logger.info("No legacy embedding models configured")

    logger.info("\n=== Recommendation Pipeline ===")
    if config.recommend_pipeline:
        rp = config.recommend_pipeline
        logger.info("Data cache: {}", rp.data.cache_dir)
        logger.info("Embedding columns: {}", ", ".join(rp.data.embedding_columns))
        logger.info("Categories: {}", ", ".join(rp.data.categories))
        logger.info("Trainer seed: {}, bg_sample_rate: {}", rp.trainer.seed, rp.trainer.bg_sample_rate)
        logger.info("Predict output: {}", rp.predict.output_path)
    else:
        logger.info("Not configured")

    logger.info("\n=== Summary Pipeline ===")
    if config.summary_pipeline:
        sp = config.summary_pipeline
        logger.info("PDF output: {}", sp.pdf.output_dir)
        logger.info("Model alias: {}", sp.pdf.model)
        logger.info("Language: {}, LaTeX: {}", sp.pdf.language, sp.pdf.enable_latex)
    else:
        logger.info("Not configured")

    logger.info("\n=== LLM Configurations ===")
    if config.llms:
        logger.info("Available LLMs: {}", len(config.llms))
        for llm in config.llms:
            logger.info("  - {}: {} (workers={})", llm.alias, llm.name, llm.num_workers)
    else:
        logger.info("No LLMs configured")


def _default_config_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "config" / "example.toml"


if __name__ == "__main__":
    raise SystemExit(main())
