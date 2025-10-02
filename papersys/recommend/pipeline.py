"""High-level orchestration helpers for recommendation tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger
from sklearn.linear_model import LogisticRegression

from papersys.config import AppConfig
from papersys.recommend.data import RecommendationDataLoader, RecommendationDataset
from papersys.recommend.predictor import PredictionResult, RecommendationPredictor
from papersys.recommend.trainer import RecommendationTrainer


@dataclass(slots=True)
class PipelineArtifacts:
    """Artifacts returned by a complete recommendation pipeline run."""

    dataset: RecommendationDataset
    model: LogisticRegression
    result: PredictionResult


class RecommendationPipeline:
    """Convenience wrapper that wires together loader, trainer and predictor."""

    def __init__(self, config: AppConfig, *, base_path: Optional[Path] = None) -> None:
        self._config = config
        self._loader = RecommendationDataLoader(config, base_path=base_path)
        self._trainer = RecommendationTrainer(config)
        self._predictor = RecommendationPredictor(config)

    def describe_sources(self) -> None:
        sources = self._loader.describe_sources()
        missing = sources.missing()
        logger.info("Preference directory: {}", sources.preference_dir)
        logger.info(
            "Metadata directory: {} (pattern={})",
            sources.metadata_dir,
            sources.metadata_pattern,
        )
        logger.info("Embeddings root: {}", sources.embeddings_root)
        for alias, directory in sources.embedding_dirs().items():
            logger.info("  - embedding[%s]: %s", alias, directory)
        if sources.summarized_dir is not None:
            logger.info("Summarized directory: {}", sources.summarized_dir)
        if missing:
            logger.warning("Missing required inputs: {}", ", ".join(missing))

    def run(self, *, force_include_all: bool = False) -> PipelineArtifacts:
        dataset = self._loader.load()
        if dataset.preferred.is_empty() or dataset.background.is_empty():
            raise ValueError("Dataset is incomplete; ensure preferences and cache data are available")
        model = self._trainer.train(dataset)
        result = self._predictor.predict(
            model,
            dataset.background,
            force_include_all=force_include_all,
        )
        return PipelineArtifacts(dataset=dataset, model=model, result=result)
