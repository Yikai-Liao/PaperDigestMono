"""Command line interface for the papersys toolkit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn
from loguru import logger

from .config import AppConfig, load_config
from .config.inspector import check_config, explain_config
from .recommend import RecommendationDataLoader
from .scheduler import SchedulerService
from .summary import SummaryPipeline
from .web import create_app


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
        help="(legacy) Equivalent to 'status --dry-run'",
    )

    subparsers = parser.add_subparsers(dest="command")

    status_parser = subparsers.add_parser("status", help="Show configuration and subsystem status")
    status_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load configuration and report subsystem availability",
    )

    summarize_parser = subparsers.add_parser("summarize", help="Inspect or run the summary pipeline")
    summarize_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the summary pipeline without executing external calls",
    )

    serve_parser = subparsers.add_parser("serve", help="Run the scheduler and API server")
    serve_parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to bind the API server to"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind the API server to"
    )
    serve_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Set up the scheduler and report status without running the server",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Fetch arXiv metadata via OAI-PMH")
    ingest_parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        help="Start date in YYYY-MM-DD format (defaults to config.ingestion.start_date)",
    )
    ingest_parser.add_argument(
        "--to",
        dest="until_date",
        type=str,
        help="End date in YYYY-MM-DD format (defaults to config.ingestion.end_date)",
    )
    ingest_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of records to fetch (for testing)",
    )
    ingest_parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Deduplicate CSV files after ingestion",
    )

    embed_parser = subparsers.add_parser("embed", help="Generate embeddings for paper metadata")
    embed_parser.add_argument(
        "--model",
        type=str,
        help="Model alias to use (e.g., conan_v1, jasper_v1). If not specified, uses first enabled model",
    )
    embed_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of papers to process per CSV (for testing)",
    )
    embed_parser.add_argument(
        "--backlog",
        action="store_true",
        help="Process backlog (CSV files without embeddings)",
    )

    config_parser = subparsers.add_parser("config", help="Validate and document configuration files")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    if hasattr(config_subparsers, "required"):
        config_subparsers.required = True  # type: ignore[attr-defined]

    check_parser = config_subparsers.add_parser("check", help="Validate the configuration file")
    check_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for validation results",
    )

    explain_parser = config_subparsers.add_parser("explain", help="Describe available configuration fields")
    explain_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for configuration schema",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = args.config.resolve()
    command = args.command

    if command == "config":
        return _handle_config_command(args, config_path)

    logger.info("Loading configuration from {}", config_path)
    config = load_config(AppConfig, config_path)

    if command is None:
        if args.dry_run:
            _report_system_status(config)
            return 0
        logger.warning("No command provided. Try 'status --dry-run' or 'summarize --dry-run'.")
        return 0

    if command == "status":
        if getattr(args, "dry_run", False):
            _report_system_status(config)
        else:
            logger.info("Status command currently supports --dry-run only; showing status.")
            _report_system_status(config)
        return 0

    if command == "ingest":
        if not config.ingestion or not config.ingestion.enabled:
            logger.error("Ingestion is not enabled in the configuration")
            return 1

        from papersys.ingestion import IngestionService

        service = IngestionService(config.ingestion)
        from_date = getattr(args, "from_date", None)
        until_date = getattr(args, "until_date", None)
        limit = getattr(args, "limit", None)

        logger.info("Starting ingestion: from={}, to={}, limit={}", from_date, until_date, limit)
        fetched, saved = service.fetch_and_save(
            from_date=from_date,
            until_date=until_date,
            limit=limit,
        )
        logger.info("Ingestion complete: fetched={}, saved={}", fetched, saved)

        if getattr(args, "deduplicate", False):
            logger.info("Deduplicating CSV files...")
            removed = service.deduplicate_csv_files()
            logger.info("Deduplicated {} records", removed)

        return 0

    if command == "embed":
        if not config.embedding or not config.embedding.enabled:
            logger.error("Embedding is not enabled in the configuration")
            return 1

        from papersys.embedding import EmbeddingService

        service = EmbeddingService(config.embedding)
        
        # Select model
        model_alias = getattr(args, "model", None)
        if model_alias:
            model_config = next(
                (m for m in config.embedding.models if m.alias == model_alias),
                None,
            )
            if not model_config:
                logger.error("Model {} not found in configuration", model_alias)
                return 1
        else:
            # Use first model
            if not config.embedding.models:
                logger.error("No embedding models configured")
                return 1
            model_config = config.embedding.models[0]
            logger.info("Using default model: {}", model_config.alias)

        limit = getattr(args, "limit", None)
        
        # Determine metadata directory
        if not config.ingestion or not config.ingestion.output_dir:
            logger.error("Ingestion output_dir not configured; cannot locate metadata CSV files")
            return 1
        
        metadata_dir = Path(config.ingestion.output_dir)
        
        if getattr(args, "backlog", False):
            # Process backlog
            backlog = service.detect_backlog(metadata_dir, model_config.alias)
            if not backlog:
                logger.info("No backlog found for model {}", model_config.alias)
                return 0
            
            logger.info("Processing {} files in backlog", len(backlog))
            total_count = 0
            for csv_path in backlog:
                count, output_path = service.generate_embeddings_for_csv(
                    csv_path,
                    model_config,
                    limit=limit,
                )
                total_count += count
            logger.info("Generated {} embeddings total", total_count)
        else:
            # Process all CSV files
            csv_files = list(metadata_dir.rglob("*.csv"))
            if not csv_files:
                logger.error("No CSV files found in {}", metadata_dir)
                return 1
            
            logger.info("Found {} CSV files", len(csv_files))
            total_count = 0
            for csv_path in csv_files:
                count, output_path = service.generate_embeddings_for_csv(
                    csv_path,
                    model_config,
                    limit=limit,
                )
                total_count += count
            logger.info("Generated {} embeddings total", total_count)

        return 0

    if command == "summarize":
        base_path = config.data_root or config_path.parent
        try:
            pipeline = SummaryPipeline(config, base_path=base_path)
        except ValueError as exc:
            logger.error("Cannot initialise summary pipeline: {}", exc)
            return 1

        if getattr(args, "dry_run", False):
            pipeline.run([], dry_run=True)
            return 0

        logger.warning("Summary execution requires input data which is not wired yet. Use --dry-run for checks.")
        return 0

    if command == "serve":
        scheduler_service = SchedulerService(config, dry_run=args.dry_run)
        scheduler_service.setup_jobs()

        if args.dry_run:
            logger.info("[Dry Run] Server will not be started.")
            return 0

        app = create_app(scheduler_service)

        @app.on_event("startup")
        async def startup_event():
            logger.info("Application startup...")
            scheduler_service.start()

        @app.on_event("shutdown")
        async def shutdown_event():
            logger.info("Application shutdown...")
            scheduler_service.shutdown()

        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    logger.warning("Unknown command: {}", command)
    return 1


def _handle_config_command(args: argparse.Namespace, config_path: Path) -> int:
    config_command = getattr(args, "config_command", None)
    output_format = getattr(args, "format", "text")

    if config_command == "check":
        result, exit_code, _ = check_config(config_path)
        if output_format == "json":
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return exit_code

        if result["status"] == "ok":
            logger.info("Configuration OK: {}", result["config_path"])
            for warning in result["warnings"]:
                logger.warning(warning)
        else:
            error = result["error"]
            logger.error(
                "Configuration error ({}) for {}: {}",
                error["type"],
                result["config_path"],
                error["message"],
            )
            for detail in error.get("details", []):
                location = detail["loc"] or "<root>"
                logger.error("  - {}: {} ({})", location, detail["message"], detail["type"])
        return exit_code

    if config_command == "explain":
        fields = explain_config()
        if output_format == "json":
            print(json.dumps({"fields": fields}, indent=2, ensure_ascii=False, default=str))
            return 0

        logger.info("Configuration schema ({} fields):", len(fields))
        for field in fields:
            default_value = field["default"]
            if isinstance(default_value, (dict, list)):
                default_repr = json.dumps(default_value, ensure_ascii=False, default=str)
            elif default_value is None:
                default_repr = "None"
            else:
                default_repr = str(default_value)
            description = field["description"] or "(no description)"
            logger.info(
                "  - {name}: type={type}, required={required}, default={default}, description={description}",
                name=field["name"],
                type=field["type"],
                required="yes" if field["required"] else "no",
                default=default_repr,
                description=description,
            )
        return 0

    logger.warning("Unknown config subcommand: {}", config_command)
    return 1


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

    logger.info("\n=== Ingestion Configuration ===")
    if config.ingestion:
        ing = config.ingestion
        logger.info("Enabled: {}", ing.enabled)
        logger.info("Output dir: {}", ing.output_dir)
        logger.info("Categories: {}", ", ".join(ing.categories) if ing.categories else "all")
        logger.info("Batch size: {}, Max retries: {}", ing.batch_size, ing.max_retries)
    else:
        logger.info("Not configured")

    logger.info("\n=== Embedding Configuration ===")
    if config.embedding:
        emb = config.embedding
        logger.info("Enabled: {}", emb.enabled)
        logger.info("Output dir: {}", emb.output_dir)
        logger.info("Auto-fill backlog: {}", emb.auto_fill_backlog)
        logger.info("Configured models: {}", len(emb.models))
        for model in emb.models:
            logger.info("  - {}: {} (dim={})", model.alias, model.name, model.dimension)
    else:
        logger.info("Not configured")

    logger.info("\n=== Recommendation Pipeline ===")
    if config.recommend_pipeline:
        rp = config.recommend_pipeline
        logger.info("Data cache: {}", rp.data.cache_dir)
        logger.info("Embedding columns: {}", ", ".join(rp.data.embedding_columns))
        logger.info("Categories: {}", ", ".join(rp.data.categories))
        logger.info("Trainer seed: {}, bg_sample_rate: {}", rp.trainer.seed, rp.trainer.bg_sample_rate)
        logger.info("Predict output: {}", rp.predict.output_path)
        try:
            base_path = config.data_root or Path.cwd()
            loader = RecommendationDataLoader(config, base_path=base_path)
            sources = loader.describe_sources()
            missing = set(sources.missing())
            logger.info(
                "Preference dir: {} (exists={})",
                sources.preference_dir,
                "preference_dir" not in missing,
            )
            logger.info(
                "Cache dir: {} (exists={})",
                sources.cache_dir,
                "cache_dir" not in missing,
            )
        except Exception as exc:
            logger.debug("Recommendation data loader inspection failed: {}", exc)
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
