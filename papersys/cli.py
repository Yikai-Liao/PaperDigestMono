"""Command line interface for the papersys toolkit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datetime import datetime, timezone

import polars as pl
import re
import typer
import uvicorn
from loguru import logger

from .config import AppConfig, load_config
from .config.embedding import EmbeddingConfig, EmbeddingModelConfig
from .config.inspector import check_config, explain_config
from .migration import LegacyMigrator, MigrationConfig as LegacyMigrationConfig
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
migrate_app = typer.Typer(help="Data migration helpers")
app.add_typer(migrate_app, name="migrate")


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


def _extract_year_from_paper_id(paper_id: str) -> str | None:
    clean = paper_id.strip()
    if not clean:
        return None

    new_style = re.match(r"^(?P<yy>\d{2})(?P<mm>\d{2})\.\d{4,5}(?:v\d+)?$", clean)
    if new_style:
        year = 2000 + int(new_style.group("yy"))
        return f"{year:04d}"

    legacy = re.match(r"^[a-z\-]+/(?P<yy>\d{2})(?P<mm>\d{2})\d+(?:v\d+)?$", clean, re.IGNORECASE)
    if legacy:
        yy = int(legacy.group("yy"))
        year = 1900 + yy if yy >= 91 else 2000 + yy
        return f"{year:04d}"

    return None


def _fallback_year_from_path(path: Path) -> str | None:
    parts = [path.parent.name, path.stem]
    for token in parts:
        for piece in token.replace("_", "-").split("-"):
            if piece.isdigit() and len(piece) == 4:
                return piece
    return None


def _raise_for_year(paper_id: str, source: Path) -> str:
    raise ValueError(f"Cannot determine publication year for paper_id '{paper_id}' from {source}")


def _collect_embedding_inputs(
    metadata_paths: list[Path],
    limit: int | None,
    skip_map: dict[str, set[str]] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Load metadata CSV files and compose embedding inputs."""

    frames: list[pl.DataFrame] = []
    for path in metadata_paths:
        if not path.exists():
            logger.warning("Metadata file not found: {}", path)
            continue
        default_year = _fallback_year_from_path(path)

        frame = pl.read_csv(
            path,
            columns=["paper_id", "title", "abstract"],
            schema_overrides={
                "paper_id": pl.String,
                "title": pl.String,
                "abstract": pl.String,
            },
        ).with_columns(
            pl.concat_str(
                [
                    pl.col("title").fill_null(""),
                    pl.lit("\n\n"),
                    pl.col("abstract").fill_null(""),
                ],
            )
            .str.strip_chars()
            .alias("__embedding_text"),
            pl.col("paper_id")
            .map_elements(
                lambda pid, fallback=default_year: (
                    _extract_year_from_paper_id(pid) or fallback or (_raise_for_year(pid, path))
                )
            )
            .alias("__year"),
        )

        frames.append(
            frame.select(
                pl.col("paper_id").cast(pl.String),
                pl.col("__embedding_text").alias("text"),
                pl.col("__year").alias("year"),
            )
        )

    if not frames:
        return [], [], []

    combined = pl.concat(frames, how="vertical_relaxed")
    combined = combined.filter(pl.col("paper_id").str.len_bytes() > 0)
    if skip_map:
        combined = combined.filter(
            pl.struct(["year", "paper_id"]).map_elements(
                lambda row: row["paper_id"] not in skip_map.get(row["year"], set())
            )
        )
    combined = combined.unique(subset=["paper_id"], keep="first", maintain_order=True)

    if limit is not None:
        combined = combined.head(limit)

    return (
        combined["text"].to_list(),
        combined["paper_id"].to_list(),
        combined["year"].to_list(),
    )


def _write_embeddings_output(
    service: "EmbeddingService",
    model_config: EmbeddingModelConfig,
    paper_ids: list[str],
    embeddings: Any,
    years: list[str],
    *,
    overwrite: bool,
) -> Path:
    """Persist generated embeddings to Parquet format."""

    model_dir = service.output_dir / model_config.alias
    model_dir.mkdir(parents=True, exist_ok=True)

    vectors = embeddings.tolist()
    result_paths: set[Path] = set()
    timestamp = datetime.now(timezone.utc).isoformat()

    grouped: dict[str, list[int]] = {}
    for idx, year in enumerate(years):
        grouped.setdefault(year, []).append(idx)

    for year, indices in grouped.items():
        subset_ids = [paper_ids[i] for i in indices]
        subset_vectors = [vectors[i] for i in indices]
        year_frame = pl.DataFrame(
            {
                "paper_id": subset_ids,
                "embedding": subset_vectors,
                "generated_at": [timestamp] * len(subset_ids),
                "model_dim": [model_config.dimension] * len(subset_ids),
                "source": ["papersys.embedding.service"] * len(subset_ids),
            }
        ).with_columns(pl.col("model_dim").cast(pl.UInt32)).unique(
            subset=["paper_id"], keep="first", maintain_order=True
        )

        output_path = model_dir / f"{year}.parquet"
        result_paths.add(output_path)

        if output_path.exists() and not overwrite:
            existing = pl.read_parquet(output_path)
            existing_aligned, new_aligned = _prepare_embedding_frames(
                existing, year_frame, model_config, timestamp
            )
            combined = pl.concat([existing_aligned, new_aligned], how="vertical_relaxed")
            combined.unique(subset=["paper_id"], keep="first", maintain_order=True).write_parquet(output_path)
        else:
            year_frame.write_parquet(output_path)

    # return last processed path for logging convenience
    return next(iter(result_paths)) if result_paths else model_dir


def _prepare_embedding_frames(
    existing_frame: pl.DataFrame,
    new_frame: pl.DataFrame,
    model_config: EmbeddingModelConfig,
    timestamp: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Align existing and new frames to share the same schema before concatenation."""

    all_columns: list[str] = []
    seen: set[str] = set()
    for col in list(existing_frame.columns) + list(new_frame.columns):
        if col not in seen:
            seen.add(col)
            all_columns.append(col)

    def _ensure_columns(frame: pl.DataFrame) -> pl.DataFrame:
        result = frame
        for column in all_columns:
            if column in result.columns:
                continue
            if column == "generated_at":
                result = result.with_columns(pl.lit(timestamp).alias("generated_at"))
            elif column == "model_dim":
                result = result.with_columns(
                    pl.lit(model_config.dimension).cast(pl.UInt32).alias("model_dim")
                )
            elif column == "source":
                result = result.with_columns(pl.lit("papersys.embedding.service").alias("source"))
            else:
                result = result.with_columns(pl.lit(None).alias(column))
        return result.select(all_columns)

    return _ensure_columns(existing_frame), _ensure_columns(new_frame)


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


@migrate_app.command("legacy")
def migrate_legacy(
    ctx: typer.Context,
    year: list[int] = typer.Option(None, "--year", help="Year to migrate (repeatable)"),
    model: list[str] = typer.Option(None, "--model", help="Embedding model alias to export"),
    output_root: Path | None = typer.Option(
        None,
        "--output-root",
        help="Destination root for migrated data (defaults to config.data_root)",
    ),
    reference_root: Path = typer.Option(
        Path("reference"),
        "--reference-root",
        help="Root directory of legacy repositories",
    ),
    hf_dataset: str = typer.Option(
        "lyk/ArxivEmbedding",
        "--hf-dataset",
        help="Hugging Face dataset id for metadata embeddings",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without writing files"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    cache_dir: Path | None = typer.Option(
        None,
        "--cache-dir",
        help="Optional cache directory for HF downloads",
    ),
    max_retries: int = typer.Option(
        3,
        "--max-retries",
        min=1,
        help="Maximum download attempts for Hugging Face artifacts",
    ),
    retry_wait: float = typer.Option(
        1.0,
        "--retry-wait",
        min=0.0,
        help="Base wait seconds before retrying downloads",
    ),
    strict: bool = typer.Option(
        True,
        "--strict/--no-strict",
        help="Fail the run when validation detects schema issues",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()
    config_dir = state.config_path.parent

    if output_root is None:
        data_root = config.data_root
        if data_root is None:
            resolved_output = (config_dir / "data").resolve()
        elif data_root.is_absolute():
            resolved_output = data_root
        else:
            resolved_output = (config_dir / data_root).resolve()
    else:
        resolved_output = output_root if output_root.is_absolute() else (config_dir / output_root).resolve()

    resolved_reference = (
        reference_root
        if reference_root.is_absolute()
        else (config_dir / reference_root).resolve()
    )

    paper_digest_root = resolved_reference / "PaperDigest"
    paper_digest_action_root = resolved_reference / "PaperDigestAction"

    resolved_cache = None
    if cache_dir is not None:
        resolved_cache = cache_dir if cache_dir.is_absolute() else (config_dir / cache_dir)
        resolved_cache = resolved_cache.resolve()

    migration_config = LegacyMigrationConfig(
        output_root=resolved_output,
        reference_roots=(paper_digest_root, paper_digest_action_root),
        hf_dataset=hf_dataset or None,
        years=tuple(year) if year else None,
        models=tuple(model) if model else None,
        dry_run=dry_run,
        force=force,
        cache_dir=resolved_cache,
        max_retries=max_retries,
        retry_wait=retry_wait,
        strict_validation=strict,
    )

    try:
        migrator = LegacyMigrator(migration_config)
        report = migrator.run()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Migration run failed: {}", exc)
        _exit(1)
        return

    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


@app.command(help="Generate summaries for recommended papers")
def summarize(
    ctx: typer.Context,
    input: Path | None = typer.Option(
        None,
        "--input",
        help="Path to recommended output (recommended.parquet/jsonl). Defaults to latest run",
    ),
    limit: int | None = typer.Option(
        None,
        help="Maximum number of papers to summarise",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Inspect the summary pipeline without generating artefacts",
    ),
) -> None:
    state = _get_state(ctx)
    config = state.ensure_config()
    if config.summary_pipeline is None:
        logger.error("Summary pipeline is not configured")
        _exit(1)

    base_path = config.data_root
    if base_path is None:
        base_path = state.config_path.parent
    elif not base_path.is_absolute():
        base_path = (state.config_path.parent / base_path).resolve()

    try:
        pipeline = SummaryPipeline(config, base_path=base_path)
    except (ValueError, EnvironmentError) as exc:
        logger.error("Cannot initialise summary pipeline: {}", exc)
        _exit(1)
        return

    pipeline.describe_sources()

    if dry_run:
        pipeline.run([], dry_run=True)
        logger.info("[Dry Run] Summary pipeline was not executed.")
        return

    resolved_input = input
    if resolved_input is not None and not resolved_input.is_absolute():
        resolved_input = (base_path / resolved_input).resolve()

    if resolved_input is None:
        resolved_input = _discover_latest_recommendation_output(base_path)
        if resolved_input is None:
            logger.error(
                "Could not locate latest recommendation output. Specify --input explicitly."
            )
            _exit(1)
            return

    try:
        sources = pipeline.load_sources_from_recommendations(resolved_input, limit=limit)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to load recommendation file {}: {}", resolved_input, exc)
        _exit(1)
        return

    if not sources:
        logger.warning("No candidates found in {}; nothing to summarise", resolved_input)
        return

    report = pipeline.run_and_save(sources, limit=limit)

    logger.info("Summary JSONL updated at {}", report.jsonl_path)
    logger.info("Summary manifest written to {}", report.manifest_path)
    logger.info("Markdown outputs available in {}", report.markdown_dir)


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
    overwrite: bool = typer.Option(
        False,
        "--overwrite/--no-overwrite",
        help="Recompute embeddings for all papers even if outputs exist",
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
        logger.warning("Backlog processing is no longer supported; running full embedding instead.")

    csv_files = sorted(path for path in metadata_dir.glob("metadata-*.csv") if path.is_file())
    if not csv_files:
        csv_files = [path for path in metadata_dir.rglob("*.csv") if path.is_file()]

    if not csv_files:
        logger.error("No metadata CSV files found in {}", metadata_dir)
        _exit(1)

    logger.info("Found {} metadata files", len(csv_files))

    existing_ids_map: dict[str, set[str]] = {}
    if not overwrite:
        model_dir = service.output_dir / model_config.alias
        if model_dir.exists():
            for parquet_path in model_dir.glob("*.parquet"):
                try:
                    year = parquet_path.stem
                    existing_column = pl.read_parquet(parquet_path, columns=["paper_id"])
                    existing_ids_map[year] = set(existing_column["paper_id"].to_list())
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Failed to load existing embeddings from {}: {}", parquet_path, exc)
        total_skipped = sum(len(ids) for ids in existing_ids_map.values())
        if total_skipped:
            logger.info("Skipping {} already embedded papers", total_skipped)

    texts, paper_ids, years = _collect_embedding_inputs(
        csv_files,
        limit,
        skip_map=existing_ids_map if not overwrite else None,
    )
    if not texts:
        logger.info("No new papers require embeddings for model {}", model_config.alias)
        return

    embeddings = service.embed_texts(texts, model_config)
    output_path = _write_embeddings_output(
        service,
        model_config,
        paper_ids,
        embeddings,
        years,
        overwrite=overwrite,
    )

    logger.info(
        "Generated {} embeddings for model {} -> {}",
        embeddings.shape[0],
        model_config.alias,
        output_path,
    )


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


def _discover_latest_recommendation_output(base_path: Path) -> Path | None:
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
