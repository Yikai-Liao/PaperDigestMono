"""Training utilities for the recommendation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import polars as pl
from loguru import logger
from sklearn.linear_model import LogisticRegression

from papersys.config import AppConfig, RecommendPipelineConfig
from papersys.recommend.data import RecommendationDataset


@dataclass(slots=True)
class TrainingSet:
    """Feature matrix and target vector used for model training."""

    features: np.ndarray
    labels: np.ndarray


class RecommendationTrainer:
    """Train a logistic regression model using user preferences."""

    def __init__(self, config: AppConfig) -> None:
        if config.recommend_pipeline is None:
            raise ValueError("recommend_pipeline config is required for training")
        self._config = config
        self._pipeline_cfg: RecommendPipelineConfig = config.recommend_pipeline

    # ------------------------------------------------------------------
    def build_training_set(self, dataset: RecommendationDataset) -> TrainingSet:
        embedding_columns = self._pipeline_cfg.data.embedding_columns
        if dataset.preferred.is_empty():
            raise ValueError("Preferred dataset is empty; cannot train model")
        if not embedding_columns:
            raise ValueError("No embedding columns configured")

        positive_df = dataset.preferred
        positive_df = positive_df.with_columns(
            pl.when(pl.col("preference") == "like")
            .then(1)
            .otherwise(0)
            .alias("__label__")
        )
        positives = positive_df.filter(pl.col("__label__") == 1)
        if positives.is_empty():
            raise ValueError("No positive samples ('like') available for training")

        background_df = dataset.background
        negative_sample = self._sample_background(background_df, positives.height)
        negative_sample = negative_sample.with_columns(pl.lit(0).alias("__label__"))

        combined = pl.concat([positives, negative_sample], how="vertical")
        features = _stack_embeddings(combined, embedding_columns)
        labels = combined.select("__label__").to_numpy().ravel()

        logger.info(
            "Training dataset prepared with {} positive and {} negative samples",
            positives.height,
            negative_sample.height,
        )
        return TrainingSet(features=features, labels=labels)

    def train(self, dataset: RecommendationDataset) -> LogisticRegression:
        training_set = self.build_training_set(dataset)

        trainer_cfg = self._pipeline_cfg.trainer
        logistic_cfg = trainer_cfg.logistic_regression
        model = LogisticRegression(
            C=logistic_cfg.C,
            max_iter=logistic_cfg.max_iter,
            random_state=trainer_cfg.seed,
            class_weight="balanced",
        )
        model.fit(training_set.features, training_set.labels)
        logger.info("Logistic regression model training completed")
        return model

    # ------------------------------------------------------------------
    def _sample_background(self, background_df: pl.DataFrame, positive_count: int) -> pl.DataFrame:
        if background_df.is_empty():
            raise ValueError("Background dataset is empty; cannot sample negatives")
        bg_sample_rate = self._pipeline_cfg.trainer.bg_sample_rate
        target_negative = max(1, int(bg_sample_rate * positive_count))
        if background_df.height <= target_negative:
            logger.info(
                "Background smaller than target sample size ({} <= {}), using full background",
                background_df.height,
                target_negative,
            )
            return background_df
        sampled = background_df.sample(
            n=target_negative,
            seed=self._pipeline_cfg.trainer.seed,
        )
        return sampled


def _stack_embeddings(frame: pl.DataFrame, columns: Iterable[str]) -> np.ndarray:
    """Convert list-based embedding columns into a dense feature matrix."""

    arrays: list[np.ndarray] = []
    for column in columns:
        series = frame[column]
        vectors = [np.asarray(item, dtype=np.float32) for item in series.to_list()]
        arrays.append(np.vstack(vectors))
    return np.hstack(arrays)
