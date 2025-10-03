"""Command line interface for the papersys toolkit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
import uvicorn
from loguru import logger

from .config import AppConfig, load_config
from .config.embedding import EmbeddingConfig, EmbeddingModelConfig
from .config.inspector import check_config, explain_config
from .recommend import RecommendationDataLoader, RecommendationPipeline
from .scheduler import SchedulerService
from .summary import SummaryPipeline
from .web import create_app

if TYPE_CHECKING:
    from .embedding import EmbeddingService


@dataclass(slots=True)
class CLIState:
    """Holds shared state between Typer commands."""

    config_path: Path
    legacy_dry_run: bool = False
    _config: AppConfig | None = None

    def ensure_config(self) -> AppConfig:
        if self._config is None:
            logger.info("Loading configuration from {}", self.config_path)
            self._config = load_config(AppConfig, self.config_path)
        return self._config


app = typer.Typer(help="Papersys orchestration helpers")
config_app = typer.Typer(help="Validate and document configuration files")
app.add_typer(config_app, name="config")


def _default_config_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "config" / "example.toml"


def _normalize_format(value: str) -> str:
    return value.lower()


def _get_state(ctx: typer.Context) -> CLIState:
    state = ctx.obj
    if not isinstance(state, CLIState):  # pragma: no cover - defensive guard
        raise RuntimeError("CLI context is not initialised")
    return state


def _exit(code: int) -> None:
    raise typer.Exit(code)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    config: Path = typer.Option(
        _default_config_path(),
        help="Path to the TOML configuration file",
    ),
    dry_run: bool = typer.Option(
        False,
        help="(legacy) Equivalent to 'status --dry-run' when no command is provided",
    ),
) -> None:
    """Initialise CLI state and handle legacy --dry-run usage."""

    state = CLIState(config_path=config.resolve(), legacy_dry_run=dry_run)
    ctx.obj = state

    if ctx.invoked_subcommand is None:
        config_obj = state.ensure_config()
        if dry_run:
            _report_system_status(config_obj)
            _exit(0)
        logger.warning(
            "No command provided. Try 'status --dry-run' or 'summarize --dry-run'."
        )
        _exit(0)


@app.command(help="Show configuration and subsystem status")
def status(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        help="Load configuration and report subsystem availability",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()

    if dry_run or state.legacy_dry_run:
        _report_system_status(config)
        return

    logger.info("Status command currently supports --dry-run only; showing status.")
    _report_system_status(config)


@app.command(help="Inspect or run the summary pipeline")
def summarize(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        help="Validate the summary pipeline without executing external calls",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()
    base_path = config.data_root or state.config_path.parent

    try:
        pipeline = SummaryPipeline(config, base_path=base_path)
    except ValueError as exc:
        logger.error("Cannot initialise summary pipeline: {}", exc)
        _exit(1)
        return

    if dry_run:
        pipeline.run([], dry_run=True)
        return

    logger.warning(
        "Summary execution requires input data which is not wired yet. Use --dry-run for checks."
    )


@app.command(help="Run the scheduler and API server")
def serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", help="Host to bind the API server to"),
    port: int = typer.Option(8000, help="Port to bind the API server to"),
    dry_run: bool = typer.Option(
        False,
        help="Set up the scheduler and report status without running the server",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()

    scheduler_service = SchedulerService(config, dry_run=dry_run)
    scheduler_service.setup_jobs()

    if dry_run:
        logger.info("[Dry Run] Server will not be started.")
        return

    app_instance = create_app(scheduler_service)

    @app_instance.on_event("startup")
    async def startup_event() -> None:
        logger.info("Application startup...")
        scheduler_service.start()

    @app_instance.on_event("shutdown")
    async def shutdown_event() -> None:
        logger.info("Application shutdown...")
        scheduler_service.shutdown()

    uvicorn.run(app_instance, host=host, port=port)


@app.command(help="Fetch arXiv metadata via OAI-PMH")
def ingest(
    ctx: typer.Context,
    from_date: str | None = typer.Option(
        None,
        "--from",
        help="Start date in YYYY-MM-DD format (defaults to config.ingestion.start_date)",
    ),
    until_date: str | None = typer.Option(
        None,
        "--to",
        help="End date in YYYY-MM-DD format (defaults to config.ingestion.end_date)",
    ),
    limit: int | None = typer.Option(
        None,
        help="Maximum number of records to fetch (for testing)",
    ),
    deduplicate: bool = typer.Option(
        False,
        help="Deduplicate CSV files after ingestion",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()

    ingestion_cfg = config.ingestion
    if ingestion_cfg is None or not ingestion_cfg.enabled:
        logger.error("Ingestion is not enabled in the configuration")
        _exit(1)

    assert ingestion_cfg is not None
    from papersys.ingestion import IngestionService

    base_path = config.data_root
    if base_path is None:
        base_path = state.config_path.parent
    elif not base_path.is_absolute():
        base_path = (state.config_path.parent / base_path).resolve()

    service = IngestionService(ingestion_cfg, base_path=base_path)

    logger.info("Starting ingestion: from={}, to={}, limit={}", from_date, until_date, limit)
    fetched, saved = service.fetch_and_save(
        from_date=from_date,
        until_date=until_date,
        limit=limit,
    )
    logger.info("Ingestion complete: fetched={}, saved={}", fetched, saved)

    if deduplicate:
        logger.info("Deduplicating CSV files...")
        removed = service.deduplicate_csv_files()
        logger.info("Deduplicated {} records", removed)


@app.command(help="Generate embeddings for paper metadata")
def embed(
    ctx: typer.Context,
    model: str | None = typer.Option(
        None,
        help="Model alias to use (e.g., conan_v1, jasper_v1). If not specified, uses first enabled model",
    ),
    limit: int | None = typer.Option(
        None,
        help="Maximum number of papers to process per CSV (for testing)",
    ),
    backlog: bool = typer.Option(
        False,
        help="Process backlog (CSV files without embeddings)",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()

    embedding_cfg = config.embedding
    if embedding_cfg is None or not embedding_cfg.enabled:
        logger.error("Embedding is not enabled in the configuration")
        _exit(1)

    from papersys.embedding import EmbeddingService

    assert embedding_cfg is not None
    base_path = config.data_root
    if base_path is None:
        base_path = state.config_path.parent
    elif not base_path.is_absolute():
        base_path = (state.config_path.parent / base_path).resolve()

    service = EmbeddingService(embedding_cfg, base_path=base_path)

    model_config = _select_embedding_model(embedding_cfg, model)
    if model_config is None:
        _exit(1)
        return

    ingestion_cfg = config.ingestion
    if ingestion_cfg is None or not ingestion_cfg.output_dir:
        logger.error("Ingestion output_dir not configured; cannot locate metadata CSV files")
        _exit(1)

    assert ingestion_cfg is not None

    metadata_dir_raw = Path(ingestion_cfg.output_dir)
    metadata_dir = metadata_dir_raw if metadata_dir_raw.is_absolute() else base_path / metadata_dir_raw

    if backlog:
        backlog_df = service.detect_backlog(metadata_dir, model_config)
        if backlog_df.is_empty():
            logger.info("No backlog items found for model {}", model_config.alias)
            return

        metadata_paths = (
            backlog_df.select("origin").unique()["origin"].to_list()
        )
        logger.info(
            "Processing {} metadata files from backlog for model {}",
            len(metadata_paths),
            model_config.alias,
        )
        total_count = 0
        for path_str in metadata_paths:
            csv_path = Path(path_str)
            if not csv_path.exists():
                logger.warning("Backlog metadata file not found: {}", csv_path)
                continue
            count, _ = service.generate_embeddings_for_csv(
                csv_path,
                model_config,
                limit=limit,
            )
            total_count += count
            service.refresh_backlog(metadata_dir, model_config)

        logger.info("Generated {} embeddings from backlog", total_count)
        return

    csv_files = sorted(path for path in metadata_dir.glob("metadata-*.csv") if path.is_file())
    if not csv_files:
        csv_files = [
            path
            for path in metadata_dir.rglob("*.csv")
            if path.is_file() and path.name != "latest.csv"
        ]

    if not csv_files:
        logger.error("No metadata CSV files found in {}", metadata_dir)
        _exit(1)

    logger.info("Found {} CSV files", len(csv_files))
    total_count = 0
    for csv_path in csv_files:
        count, _ = service.generate_embeddings_for_csv(
            csv_path,
            model_config,
            limit=limit,
        )
        total_count += count
    logger.info("Generated {} embeddings total", total_count)
    service.refresh_backlog(metadata_dir, model_config)


@app.command(help="Run the recommendation pipeline")
def recommend(
    ctx: typer.Context,
    force_all: bool = typer.Option(
        False,
        "--force-all",
        help="Force include all scored candidates in the recommendation output",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Inspect data sources without running training or prediction",
    ),
    output_dir: Path | None = typer.Option(
        None,
        help="Override output directory for recommendation artifacts",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()

    if config.recommend_pipeline is None:
        logger.error("Recommendation pipeline is not configured")
        _exit(1)

    base_path = config.data_root
    if base_path is None:
        base_path = state.config_path.parent
    elif not base_path.is_absolute():
        base_path = (state.config_path.parent / base_path).resolve()

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


@config_app.command(help="Validate the configuration file")
def check(
    ctx: typer.Context,
    format: str = typer.Option(  # noqa: A002 - match CLI option name
        "text",
        "--format",
        case_sensitive=False,
        help="Output format for validation results",
        callback=_normalize_format,
    ),
) -> None:
    state = _get_state(ctx)
    result, exit_code, _ = check_config(state.config_path)

    if format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        _exit(exit_code)

    if result["status"] == "ok":
        logger.info("Configuration OK: {}", result["config_path"])
        for warning in result["warnings"]:
            logger.warning(warning)
    else:
        error: dict[str, Any] = result["error"]
        logger.error(
            "Configuration error ({}) for {}: {}",
            error["type"],
            result["config_path"],
            error["message"],
        )
        for detail in error.get("details", []):
            location = detail["loc"] or "<root>"
            logger.error("  - {}: {} ({})", location, detail["message"], detail["type"])

    _exit(exit_code)


@config_app.command(help="Describe available configuration fields")
def explain(
    format: str = typer.Option(  # noqa: A002 - match CLI option name
        "text",
        "--format",
        case_sensitive=False,
        help="Output format for configuration schema",
        callback=_normalize_format,
    ),
) -> None:
    fields = explain_config()

    if format == "json":
        print(json.dumps({"fields": fields}, indent=2, ensure_ascii=False, default=str))
        return

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


def _select_embedding_model(
    embedding_cfg: EmbeddingConfig, model_alias: str | None
) -> EmbeddingModelConfig | None:
    if model_alias:
        model_config = next(
            (m for m in embedding_cfg.models if m.alias == model_alias),
            None,
        )
        if not model_config:
            logger.error("Model {} not found in configuration", model_alias)
            return None
        return model_config

    if not embedding_cfg.models:
        logger.error("No embedding models configured")
        return None

    model_config = embedding_cfg.models[0]
    logger.info("Using default model: {}", model_config.alias)
    return model_config




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
        logger.info("Preference dir: {}", rp.data.preference_dir)
        logger.info(
            "Metadata dir: {} (pattern={})",
            rp.data.metadata_dir,
            rp.data.metadata_pattern,
        )
        logger.info("Embeddings root: {}", rp.data.embeddings_root)
        logger.info("Embedding columns: {}", ", ".join(rp.data.embedding_columns))
        logger.info("Categories: {}", ", ".join(rp.data.categories))
        logger.info("Trainer seed: {}, bg_sample_rate: {}", rp.trainer.seed, rp.trainer.bg_sample_rate)
        logger.info("Predict output dir: {}", rp.predict.output_dir)
        logger.info("Predict file: {}", rp.predict.output_path)
        logger.info("Recommended file: {}", rp.predict.recommended_path)
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
                "Metadata dir: {} (exists={})",
                sources.metadata_dir,
                "metadata_dir" not in missing,
            )
            for alias, directory in sources.embedding_dirs().items():
                logger.info(
                    "Embedding[%s]: %s (exists=%s)",
                    alias,
                    directory,
                    f"embedding_dir[{alias}]" not in missing,
                )
        except Exception as exc:
            logger.debug("Recommendation data loader inspection failed: {}", exc)
    else:
        logger.info("Not configured")

    logger.info("\n=== Summary Pipeline ===")
    if config.summary_pipeline:
        sp = config.summary_pipeline
        logger.info("PDF output: {}", sp.pdf.output_dir)
        logger.info("Fetch LaTeX source: {}", sp.pdf.fetch_latex_source)
        logger.info("Model alias: {}", sp.llm.model)
        logger.info("Language: {}, LaTeX: {}", sp.llm.language, sp.llm.enable_latex)
    else:
        logger.info("Not configured")

    logger.info("\n=== LLM Configurations ===")
    if config.llms:
        logger.info("Available LLMs: {}", len(config.llms))
        for llm in config.llms:
            logger.info("  - {}: {} (workers={})", llm.alias, llm.name, llm.num_workers)
    else:
        logger.info("No LLMs configured")


def main(argv: list[str] | None = None) -> int:
    """Entry point compatible with setuptools console scripts."""

    try:
        result = app(args=argv, standalone_mode=False)
    except typer.Exit as exc:  # pragma: no cover - Typer translates exit codes
        return exc.exit_code
    if isinstance(result, int):
        return result
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
