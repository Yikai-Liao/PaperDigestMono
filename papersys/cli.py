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
    logger.info("Data root: {}", config.data_root)
    logger.info("Scheduler enabled: {}", config.scheduler_enabled)
    if config.embedding_models:
        logger.info("Embedding models ({}): {}", len(config.embedding_models), ", ".join(config.embedding_models))
    else:
        logger.info("No embedding models configured")
    logger.info("Logging level: {}", config.logging_level)


def _default_config_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "config" / "example.toml"


if __name__ == "__main__":
    raise SystemExit(main())
