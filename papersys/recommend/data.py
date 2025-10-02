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
    metadata_dir: Path
    metadata_pattern: str
    embeddings_root: Path
    embedding_aliases: tuple[str, ...]
    summarized_dir: Path | None

    def embedding_dirs(self) -> dict[str, Path]:
        return {alias: self.embeddings_root / alias for alias in self.embedding_aliases}

    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.preference_dir.exists():
            missing.append("preference_dir")
        if not self.metadata_dir.exists():
            missing.append("metadata_dir")
        for alias, directory in self.embedding_dirs().items():
            if not directory.exists():
                missing.append(f"embedding_dir[{alias}]")
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
        metadata_dir = self._resolve(data_cfg.metadata_dir)
        embeddings_root = self._resolve(data_cfg.embeddings_root)
        summarized_dir = self._summarized_dir or self._resolve_optional("summarized")
        return RecommendationDataSources(
            preference_dir=preference_dir,
            metadata_dir=metadata_dir,
            metadata_pattern=data_cfg.metadata_pattern,
            embeddings_root=embeddings_root,
            embedding_aliases=tuple(data_cfg.embedding_columns),
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
            with csv_path.open("r", encoding="utf-8") as fh:
                header_line = fh.readline().strip()
            if not header_line:
                raise ValueError(f"Preference CSV {csv_path} is empty")

            field_names = [name.strip() for name in header_line.split(",") if name.strip()]
            overrides = {
                name: pl.String
                for name in field_names
                if name in {"id", "paper_id", "preference", "recorded_at"}
            }

            frame = pl.read_csv(csv_path, schema_overrides=overrides)

            if "id" not in frame.columns and "paper_id" in frame.columns:
                frame = frame.rename({"paper_id": "id"})

            if "id" not in frame.columns:
                raise ValueError(
                    f"Preference CSV {csv_path} must contain an 'id' or 'paper_id' column"
                )

            if "preference" not in frame.columns:
                raise ValueError(f"Preference CSV {csv_path} is missing 'preference' column")

            frames.append(frame.select(["id", "preference"]))
        if not frames:
            raise ValueError(f"No preference CSV files found in {preference_dir}")
        preferences = pl.concat(frames, how="vertical").unique(subset="id")
        logger.info("Loaded {} unique preference entries", preferences.height)
        return preferences

    def _load_candidates_lazy(self) -> pl.LazyFrame:
        sources = self.describe_sources()
        metadata_paths = sorted(sources.metadata_dir.glob(sources.metadata_pattern))
        if not metadata_paths:
            raise FileNotFoundError(
                f"No metadata CSV files found in {sources.metadata_dir} using pattern {sources.metadata_pattern}"
            )

        metadata_lazy = self._scan_metadata(metadata_paths)

        candidate_lazy = metadata_lazy
        for alias, directory in sources.embedding_dirs().items():
            parquet_paths = sorted(directory.glob("*.parquet"))
            if not parquet_paths:
                raise FileNotFoundError(
                    f"No parquet files found for embedding '{alias}' in {directory}"
                )
            embedding_lazy = self._scan_embedding(alias, parquet_paths)
            candidate_lazy = candidate_lazy.join(embedding_lazy, on="id", how="inner")

        return candidate_lazy.unique(subset="id")

    def _scan_metadata(self, paths: Iterable[Path]) -> pl.LazyFrame:
        scans: list[pl.LazyFrame] = []
        for csv_path in paths:
            scan = pl.scan_csv(
                str(csv_path),
                schema_overrides={
                    "paper_id": pl.String,
                    "title": pl.String,
                    "abstract": pl.String,
                    "categories": pl.String,
                    "updated_at": pl.String,
                },
            )
            scans.append(scan)

        metadata = pl.concat(scans, how="vertical") if len(scans) > 1 else scans[0]
        metadata = metadata.with_columns(
            pl.col("paper_id").alias("id"),
            pl.col("title").fill_null("").alias("title"),
            pl.col("abstract").fill_null("").alias("abstract"),
            pl.col("categories")
            .fill_null("")
            .str.split(";")
            .list.eval(pl.element().str.strip_chars())
            .alias("categories"),
            pl.col("updated_at").fill_null("").alias("updated"),
        ).select(["id", "title", "abstract", "categories", "updated"])
        return metadata.unique(subset="id")

    def _scan_embedding(self, alias: str, parquet_paths: Iterable[Path]) -> pl.LazyFrame:
        lazy = pl.scan_parquet(
            [str(path) for path in parquet_paths],
            n_rows=None,
        )
        return lazy.select(
            pl.col("paper_id").alias("id"),
            pl.col("embedding").alias(alias),
        )

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

        valid_conditions: list[pl.Expr] = []
        for column in embedding_columns:
            col_expr = pl.col(column)
            invalid_expr = (
                col_expr.is_null()
                | col_expr.list.eval(pl.element().is_null()).list.any()
                | col_expr.list.eval(~pl.element().is_finite()).list.any()
            )
            valid_conditions.append(~invalid_expr)

        condition = pl.all_horizontal(valid_conditions)
        filtered = frame.filter(condition)
        logger.info(
            "Filtered rows with null or non-finite embeddings for columns {}",
            embedding_columns,
        )
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