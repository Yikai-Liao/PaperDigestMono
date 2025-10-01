"""Data loading utilities for the recommendation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import polars as pl
from loguru import logger

from papersys.config import AppConfig, RecommendPipelineConfig


@dataclass(slots=True)
class RecommendationDataset:
    """Container for the preferred and background datasets."""

    preferred: pl.DataFrame
    background: pl.DataFrame

    @property
    def preferred_count(self) -> int:
        return self.preferred.height

    @property
    def background_count(self) -> int:
        return self.background.height


@dataclass(slots=True)
class RecommendationDataSources:
    """Resolved IO locations that feed the recommendation pipeline."""

    preference_dir: Path
    cache_dir: Path
    summarized_dir: Path | None

    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.preference_dir.exists():
            missing.append("preference_dir")
        if not self.cache_dir.exists():
            missing.append("cache_dir")
        if self.summarized_dir is not None and not self.summarized_dir.exists():
            missing.append("summarized_dir")
        return tuple(missing)


class RecommendationDataLoader:
    """Load recommendation training data from the local workspace."""

    def __init__(
        self,
        config: AppConfig,
        *,
        base_path: Path | None = None,
        summarized_dir: Path | None = None,
    ) -> None:
        if config.recommend_pipeline is None:
            raise ValueError("recommend_pipeline config is required for data loading")

        self._config = config
        self._pipeline_cfg: RecommendPipelineConfig = config.recommend_pipeline
        self._base_path = base_path or Path.cwd()
        self._summarized_dir = summarized_dir

    # ------------------------------------------------------------------
    # public API
    def describe_sources(self) -> RecommendationDataSources:
        data_cfg = self._pipeline_cfg.data
        preference_dir = self._resolve(data_cfg.preference_dir)
        cache_dir = self._resolve(data_cfg.cache_dir)
        summarized_dir = self._summarized_dir or self._resolve_optional("summarized")
        return RecommendationDataSources(
            preference_dir=preference_dir,
            cache_dir=cache_dir,
            summarized_dir=summarized_dir,
        )

    def load(self) -> RecommendationDataset:
        preferences = self._load_preferences()
        candidate_lazy = self._load_candidates_lazy()
        candidate_lazy = self._filter_by_categories(candidate_lazy)
        candidate_lazy = self._filter_valid_embeddings(candidate_lazy)
        candidate_lazy = self._apply_year_constraints(candidate_lazy)
        candidate_lazy = self._remove_known_recommendations(candidate_lazy)

        candidate_df = candidate_lazy.collect()
        logger.info(
            "Collected {} candidate rows after filtering",
            candidate_df.height,
        )
        if candidate_df.is_empty():
            return RecommendationDataset(
                preferred=pl.DataFrame(),
                background=pl.DataFrame(),
            )

        preference_ids = preferences.select("id").to_series().to_list()
        preferred_df = candidate_df.join(preferences, on="id", how="inner")
        background_df = candidate_df.filter(~pl.col("id").is_in(preference_ids))
        if not background_df.is_empty() and "preference" not in background_df.columns:
            background_df = background_df.with_columns(pl.lit("unrated").alias("preference"))

        logger.info(
            "Preferred rows: {} | background rows: {}",
            preferred_df.height,
            background_df.height,
        )
        return RecommendationDataset(preferred=preferred_df, background=background_df)

    # ------------------------------------------------------------------
    # helpers
    def _resolve(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = (self._base_path / path).resolve()
        return path

    def _resolve_optional(self, value: str | Path) -> Path:
        try:
            return self._resolve(value)
        except Exception:
            return Path(value)

    def _load_preferences(self) -> pl.DataFrame:
        sources = self.describe_sources()
        preference_dir = sources.preference_dir
        if not preference_dir.exists():
            raise FileNotFoundError(f"Preference directory not found: {preference_dir}")

        frames: list[pl.DataFrame] = []
        for csv_path in sorted(preference_dir.rglob("*.csv")):
            frames.append(
                pl.read_csv(
                    csv_path,
                    columns=["id", "preference"],
                    schema={"id": pl.String, "preference": pl.String},
                )
            )
        if not frames:
            raise ValueError(f"No preference CSV files found in {preference_dir}")
        preferences = pl.concat(frames, how="vertical").unique(subset="id")
        logger.info("Loaded {} unique preference entries", preferences.height)
        return preferences

    def _load_candidates_lazy(self) -> pl.LazyFrame:
        sources = self.describe_sources()
        cache_dir = sources.cache_dir
        if not cache_dir.exists():
            raise FileNotFoundError(f"Cache directory not found: {cache_dir}")

        parquet_paths = sorted(cache_dir.glob("*.parquet"))
        if not parquet_paths:
            raise ValueError(f"No parquet files found in {cache_dir}")

        return pl.scan_parquet([str(p) for p in parquet_paths], missing_columns="insert")

    def _filter_by_categories(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        categories = self._pipeline_cfg.data.categories
        if not categories:
            return frame
        condition = pl.col("categories").list.contains(pl.lit(categories[0]))
        for category in categories[1:]:
            condition = condition | pl.col("categories").list.contains(pl.lit(category))
        filtered = frame.filter(condition)
        logger.info("Applied category filter: {}", categories)
        return filtered

    def _filter_valid_embeddings(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        embedding_columns = self._pipeline_cfg.data.embedding_columns
        if not embedding_columns:
            return frame
        condition = pl.all_horizontal([pl.col(col).is_not_null() for col in embedding_columns])
        filtered = frame.filter(condition)
        logger.info("Filtered rows with null embeddings for columns {}", embedding_columns)
        return filtered

    def _apply_year_constraints(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        background_year = self._pipeline_cfg.data.background_start_year
        if background_year is None:
            return frame
        filtered = (
            frame.with_columns(
                pl.col("updated").str.slice(0, 4).cast(pl.Int32, strict=False).alias("__year__")
            )
            .filter(pl.col("__year__") >= background_year)
            .drop("__year__")
        )
        logger.info("Filtered background data with updated >= {}", background_year)
        return filtered

    def _remove_known_recommendations(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        summaries_dir = self.describe_sources().summarized_dir
        if summaries_dir is None or not summaries_dir.exists():
            return frame
        jsonl_files = sorted(summaries_dir.glob("*.jsonl"))
        if not jsonl_files:
            return frame
        try:
            recommended_ids = (
                pl.scan_ndjson([str(p) for p in jsonl_files])
                .select("id")
                .collect()
                .select("id")
            )
        except Exception as exc:
            logger.warning("Failed to read summarized JSONL files: {}", exc)
            return frame
        filtered = frame.filter(~pl.col("id").is_in(recommended_ids["id"]))
        logger.info(
            "Removed {} entries that already have summaries",
            recommended_ids.height,
        )
        return filtered