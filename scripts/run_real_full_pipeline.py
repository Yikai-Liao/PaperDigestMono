#!/usr/bin/env python3
"""Run the recommendation + summary pipeline against real data.

This script is designed for manual verification of the end-to-end workflow
without polluting the canonical ``data/`` directory. It reads metadata and
embeddings from the configured locations, writes all transient artefacts to
an isolated run directory, and prints lightweight diagnostics so that humans
can inspect the outputs (PDF/Markdown/JSON) for correctness.

Example usage::

    uv run --no-progress python scripts/run_real_full_pipeline.py \
        --config config/example.toml \
        --limit 3 \
        --output-dir .tmp-real-runs/latest \
        --fetch-latex

The script intentionally performs only basic sanity checks; final judgement
about output quality is left to manual review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Iterable

import polars as pl
from loguru import logger

ProjectRoot = Path(__file__).resolve().parent.parent
if str(ProjectRoot) not in sys.path:
    sys.path.insert(0, str(ProjectRoot))

from papersys.config import AppConfig, load_config
from papersys.config.llm import LLMConfig
from papersys.recommend.pipeline import RecommendationPipeline
from papersys.summary.models import SummarySource
from papersys.summary.pipeline import SummaryPipeline


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full pipeline on real data")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/example.toml"),
        help="Path to the TOML configuration file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of summaries to generate (top-N by score)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destination directory for generated artefacts (defaults to .tmp-real-runs/<timestamp>)",
    )
    parser.add_argument(
        "--force-include-all",
        action="store_true",
        help="Bypass score-based sampling and summarise all scored candidates",
    )
    parser.add_argument(
        "--fetch-latex",
        action="store_true",
        help="Force enable LaTeX source fetching regardless of config",
    )
    return parser.parse_args()


def _resolve_data_root(config: AppConfig, config_path: Path) -> Path:
    if config.data_root:
        base = config.data_root
        if not base.is_absolute():
            base = (config_path.parent / base).resolve()
        else:
            base = base.resolve()
        return base
    # Fallback: assume data directory next to config
    return (config_path.parent / "data").resolve()


def _resolve_relative(path_str: str, *, base: Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _ensure_llm_ready(config: AppConfig) -> LLMConfig:
    if config.summary_pipeline is None:
        raise RuntimeError("summary_pipeline config is required")
    alias = config.summary_pipeline.llm.model
    for llm in config.llms:
        if llm.alias == alias:
            # Accessing api_key_secret validates env references.
            _ = llm.api_key_secret
            return llm
    raise RuntimeError(f"LLM alias '{alias}' not found in configuration")


def _prepare_run_directory(desired: Path | None, *, data_root: Path) -> Path:
    if desired is None:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        desired = Path(".tmp-real-runs") / timestamp
    desired = desired.resolve()
    if desired.is_relative_to(data_root):
        raise RuntimeError(
            f"Output directory {desired} is inside data root {data_root}; choose a different location"
        )
    desired.mkdir(parents=True, exist_ok=True)
    return desired


def _build_runtime_config(
    config: AppConfig,
    *,
    run_dir: Path,
    data_root: Path,
    force_fetch_latex: bool,
) -> AppConfig:
    if config.recommend_pipeline is None:
        raise RuntimeError("recommend_pipeline config is required")
    if config.summary_pipeline is None:
        raise RuntimeError("summary_pipeline config is required")

    data_cfg = config.recommend_pipeline.data
    predict_cfg = config.recommend_pipeline.predict
    pdf_cfg = config.summary_pipeline.pdf

    updated_data = data_cfg.model_copy(
        update={
            "preference_dir": str(_resolve_relative(data_cfg.preference_dir, base=data_root)),
            "metadata_dir": str(_resolve_relative(data_cfg.metadata_dir, base=data_root)),
            "embeddings_root": str(_resolve_relative(data_cfg.embeddings_root, base=data_root)),
        }
    )

    updated_predict = predict_cfg.model_copy(
        update={
            "output_path": str((run_dir / "recommendations.parquet").resolve()),
        }
    )

    pdf_updates: dict[str, object] = {
        "output_dir": str((run_dir / "summary-output").resolve()),
    }
    if force_fetch_latex:
        pdf_updates["fetch_latex_source"] = True

    updated_pdf = pdf_cfg.model_copy(update=pdf_updates)

    updated_recommend = config.recommend_pipeline.model_copy(
        update={
            "data": updated_data,
            "predict": updated_predict,
        }
    )

    updated_summary = config.summary_pipeline.model_copy(update={"pdf": updated_pdf})

    return config.model_copy(
        update={
            "recommend_pipeline": updated_recommend,
            "summary_pipeline": updated_summary,
        }
    )


def _select_sources(recommended: pl.DataFrame, *, language: str, limit: int) -> list[SummarySource]:
    head = recommended.sort("score", descending=True)
    if limit > 0:
        head = head.head(limit)

    sources: list[SummarySource] = []
    for row in head.iter_rows(named=True):
        sources.append(
            SummarySource(
                paper_id=row["id"],
                title=row.get("title", "<missing title>"),
                abstract=row.get("abstract", ""),
                language=language,
            )
        )
    return sources


def _describe_dataset(df: pl.DataFrame, *, label: str) -> None:
    logger.info("{}: {} rows", label, df.height)
    if df.is_empty():
        return
    preview_cols = [col for col in ("id", "title", "score", "updated") if col in df.columns]
    preview = df.select(preview_cols).head(5)
    logger.info("{} preview:\n{}", label, preview)


def _validate_outputs(artifacts: Iterable, *, run_dir: Path) -> None:
    for idx, artifact in enumerate(artifacts, start=1):
        pdf_path = artifact.pdf_path
        markdown_path = artifact.markdown_path
        if not pdf_path.exists():
            logger.warning("[{}] PDF missing: {}", idx, pdf_path)
        if not markdown_path.exists():
            logger.warning("[{}] Markdown missing: {}", idx, markdown_path)
        logger.info(
            "[%d] Summary generated | pdf=%s | markdown=%s | sections=%s",
            idx,
            pdf_path.relative_to(run_dir),
            markdown_path.relative_to(run_dir),
            list(artifact.document.sections.keys()),
        )
        snippet = "\n".join(artifact.markdown.splitlines()[:12])
        logger.info("[%d] Markdown snippet:\n%s", idx, snippet)


def main() -> None:
    args = _parse_args()

    if not args.config.exists():
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)

    config = load_config(AppConfig, args.config)
    data_root = _resolve_data_root(config, args.config)
    run_dir = _prepare_run_directory(args.output_dir, data_root=data_root)

    if args.fetch_latex:
        logger.info("Force-enabling LaTeX source fetching for this run")

    try:
        llm_cfg = _ensure_llm_ready(config)
    except EnvironmentError as exc:
        logger.error("Missing LLM credentials: %s", exc)
        sys.exit(1)
    except RuntimeError as exc:
        logger.error(str(exc))
        sys.exit(1)

    runtime_config = _build_runtime_config(
        config,
        run_dir=run_dir,
        data_root=data_root,
        force_fetch_latex=args.fetch_latex,
    )

    logger.info("Run directory: %s", run_dir)
    logger.info("Using LLM alias '%s' (model=%s, base_url=%s)", llm_cfg.alias, llm_cfg.name, llm_cfg.base_url)

    recommendation = RecommendationPipeline(runtime_config)
    recommendation.describe_sources()

    try:
        artifacts = recommendation.run(force_include_all=args.force_include_all)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Recommendation pipeline failed: %s", exc)
        sys.exit(1)

    dataset = artifacts.dataset
    _describe_dataset(dataset.preferred, label="Preferred dataset")
    _describe_dataset(dataset.background, label="Background dataset")

    recommended = artifacts.result.recommended
    if recommended.is_empty():
        logger.error("No recommendations produced; aborting before summarisation")
        sys.exit(1)
    _describe_dataset(recommended, label="Recommended candidates")

    summary_language = runtime_config.summary_pipeline.llm.language  # type: ignore[union-attr]
    sources = _select_sources(recommended, language=summary_language, limit=args.limit)
    logger.info("Preparing to summarise %d papers (language=%s)", len(sources), summary_language)

    summary_pipeline = SummaryPipeline(runtime_config)
    try:
        outputs = summary_pipeline.run(sources)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Summary pipeline failed: %s", exc)
        sys.exit(1)

    if not outputs:
        logger.warning("Summary pipeline returned no artefacts")
    else:
        if len(outputs) < len(sources):
            logger.warning(
                "Summary pipeline produced %d of %d requested artefacts (some papers were skipped)",
                len(outputs),
                len(sources),
            )
        _validate_outputs(outputs, run_dir=run_dir)

    logger.info("Run complete. Inspect artefacts under %s", run_dir)


if __name__ == "__main__":
    main()