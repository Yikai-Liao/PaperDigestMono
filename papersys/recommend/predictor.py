"""Prediction utilities for the recommendation pipeline."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import polars as pl
from loguru import logger
from sklearn.linear_model import LogisticRegression

from papersys.config import AppConfig


@dataclass(slots=True)
class PredictionResult:
    """Prediction outputs including scored candidates and the recommended subset."""

    scored: pl.DataFrame
    recommended: pl.DataFrame


class RecommendationPredictor:
    """Score and sample candidate papers for recommendation."""

    def __init__(self, config: AppConfig) -> None:
        if config.recommend_pipeline is None:
            raise ValueError("recommend_pipeline config is required for prediction")
        self._config = config
        self._pipeline_cfg = config.recommend_pipeline

    # ------------------------------------------------------------------
    def predict(
        self,
        model: LogisticRegression,
        candidates: pl.DataFrame,
        *,
        force_include_all: bool = False,
        now: dt.datetime | None = None,
    ) -> PredictionResult:
        if candidates.is_empty():
            logger.warning("No candidates provided for prediction")
            empty = pl.DataFrame()
            return PredictionResult(scored=empty, recommended=empty)

        predict_cfg = self._pipeline_cfg.predict
        data_cfg = self._pipeline_cfg.data

        filtered = self._filter_by_date(candidates, predict_cfg, now=now)
        if filtered.is_empty():
            logger.warning("No candidates remain after date filtering")
            return PredictionResult(scored=filtered, recommended=filtered)

        embeddings = _stack_embeddings(filtered, data_cfg.embedding_columns)
        scores = model.predict_proba(embeddings)[:, 1]
        scored = filtered.with_columns(pl.Series("score", scores))

        if force_include_all:
            show_flags = np.ones(len(scores), dtype=bool)
        else:
            show_flags = adaptive_sample(
                scores,
                target_sample_rate=predict_cfg.sample_rate,
                high_threshold=predict_cfg.high_threshold,
                boundary_threshold=predict_cfg.boundary_threshold,
                random_state=self._pipeline_cfg.trainer.seed,
            )
        scored = scored.with_columns(pl.Series("show", show_flags.astype(np.int8)))

        recommended = scored.filter(pl.col("show") == 1)
        if not recommended.is_empty():
            recommended = recommended.drop(*data_cfg.embedding_columns, strict=False)

        logger.info(
            "Prediction complete: {} candidates scored, {} recommended",
            scored.height,
            recommended.height,
        )
        return PredictionResult(scored=scored, recommended=recommended)

    # ------------------------------------------------------------------
    def _filter_by_date(
        self,
        candidates: pl.DataFrame,
        predict_cfg,
        *,
        now: dt.datetime | None = None,
    ) -> pl.DataFrame:
        if candidates.is_empty():
            return candidates

        if predict_cfg.start_date and predict_cfg.end_date:
            logger.info(
                "Filtering candidates between {} and {}",
                predict_cfg.start_date,
                predict_cfg.end_date,
            )
            return candidates.filter(
                (pl.col("updated") >= predict_cfg.start_date)
                & (pl.col("updated") <= predict_cfg.end_date)
            )

        now = now or dt.datetime.now()
        start = (now - dt.timedelta(days=predict_cfg.last_n_days)).strftime("%Y-%m-%d")
        logger.info("Filtering candidates using last {} days since {}", predict_cfg.last_n_days, start)
        return candidates.filter(pl.col("updated") >= start)


def adaptive_sample(
    scores: np.ndarray,
    *,
    target_sample_rate: float,
    high_threshold: float,
    boundary_threshold: float,
    random_state: int,
) -> np.ndarray:
    """Select a subset of candidates based on score thresholds."""

    if scores.size == 0:
        return np.zeros(0, dtype=bool)

    rng = np.random.default_rng(random_state)
    n_samples = scores.size
    target_count = max(1, int(n_samples * target_sample_rate))

    flags = np.zeros(n_samples, dtype=bool)

    high_indices = np.where(scores >= high_threshold)[0]
    if high_indices.size >= target_count:
        chosen = rng.choice(high_indices, target_count, replace=False)
        flags[chosen] = True
        return flags

    flags[high_indices] = True
    remaining = target_count - high_indices.size

    boundary_mask = (scores >= boundary_threshold) & (scores < high_threshold)
    boundary_indices = np.where(boundary_mask)[0]
    if boundary_indices.size > 0 and remaining > 0:
        boundary_scores = scores[boundary_indices]
        weights = boundary_scores - boundary_threshold
        weights = np.clip(weights, 0, None)
        if weights.sum() == 0:
            weights = np.ones_like(boundary_scores)
        weights = weights / weights.sum()
        select_count = min(remaining, boundary_indices.size)
        chosen = rng.choice(boundary_indices, select_count, replace=False, p=weights)
        flags[chosen] = True
        remaining -= select_count

    if remaining > 0:
        low_indices = np.where(~flags)[0]
        if low_indices.size > 0:
            select_count = min(remaining, low_indices.size)
            chosen = rng.choice(low_indices, select_count, replace=False)
            flags[chosen] = True

    return flags


def _stack_embeddings(frame: pl.DataFrame, columns: Iterable[str]) -> np.ndarray:
    arrays: list[np.ndarray] = []
    for column in columns:
        series = frame[column]
        vectors = [np.asarray(item, dtype=np.float32) for item in series.to_list()]
        arrays.append(np.vstack(vectors))
    return np.hstack(arrays)
