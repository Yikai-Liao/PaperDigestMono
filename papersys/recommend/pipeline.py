"""High-level orchestration helpers for recommendation tasks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass(slots=True)
class PipelineRunReport:
    """Detailed report for an on-disk recommendation pipeline run."""

    artifacts: PipelineArtifacts
    output_dir: Path
    predictions_path: Path
    recommended_path: Path
    manifest_path: Path


def run_recommend_pipeline(config: AppConfig, *, base_path: Optional[Path] = None, force_include_all: bool = False) -> PipelineRunReport:
    """Run the full recommendation pipeline and save outputs."""
    pipeline = RecommendationPipeline(config, base_path=base_path)
    return pipeline.run_and_save(force_include_all=force_include_all)


class RecommendationPipeline:
    """Convenience wrapper that wires together loader, trainer and predictor."""

    def __init__(self, config: AppConfig, *, base_path: Optional[Path] = None) -> None:
        if config.recommend_pipeline is None:
            raise ValueError("recommend_pipeline config is required for pipeline operations")

        self._config = config
        self._pipeline_cfg = config.recommend_pipeline
        self._base_path = self._resolve_base_path(base_path)
        self._loader = RecommendationDataLoader(config, base_path=self._base_path)
        self._trainer = RecommendationTrainer(config)
        self._predictor = RecommendationPredictor(config)
        self._output_root = self._resolve_output_dir(Path(self._pipeline_cfg.predict.output_dir))

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
            logger.info("  - embedding[{}]: {}", alias, directory)
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

    def run_and_save(
        self,
        *,
        force_include_all: bool = False,
        output_dir: Path | None = None,
        run_at: datetime | None = None,
    ) -> PipelineRunReport:
        artifacts = self.run(force_include_all=force_include_all)

        run_at = run_at or datetime.now(timezone.utc)
        run_id = run_at.strftime("%Y%m%d-%H%M%S")

        if output_dir is not None:
            target_dir = output_dir if output_dir.is_absolute() else (self._base_path / output_dir).resolve()
        else:
            target_dir = (self._output_root / run_id).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        predict_cfg = self._pipeline_cfg.predict
        predictions_path = self._resolve_output_path(predict_cfg.output_path, target_dir)
        recommended_path = self._resolve_output_path(predict_cfg.recommended_path, target_dir)
        manifest_path = self._resolve_output_path(predict_cfg.manifest_path, target_dir)

        artifacts.result.scored.write_parquet(predictions_path)
        artifacts.result.recommended.write_parquet(recommended_path)

        manifest = self._build_manifest(artifacts, force_include_all=force_include_all, run_at=run_at, run_id=run_id)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(
            "Recommendation outputs saved: predictions={} recommended={} manifest={}",
            predictions_path,
            recommended_path,
            manifest_path,
        )

        return PipelineRunReport(
            artifacts=artifacts,
            output_dir=target_dir,
            predictions_path=predictions_path,
            recommended_path=recommended_path,
            manifest_path=manifest_path,
        )

    # ------------------------------------------------------------------
    def _resolve_base_path(self, base_path: Optional[Path]) -> Path:
        if base_path is not None:
            return Path(base_path).resolve()
        if self._config.data_root is not None:
            return Path(self._config.data_root).resolve()
        return Path.cwd()

    def _resolve_output_dir(self, fragment: Path) -> Path:
        if fragment.is_absolute():
            return fragment
        return (self._base_path / fragment).resolve()

    def _resolve_output_path(self, fragment: str, target_dir: Path) -> Path:
        path = Path(fragment)
        if path.is_absolute():
            return path
        return (target_dir / path).resolve()

    def _build_manifest(
        self,
        artifacts: PipelineArtifacts,
        *,
        force_include_all: bool,
        run_at: datetime,
        run_id: str,
    ) -> dict[str, object]:
        predict_cfg = self._pipeline_cfg.predict
        data_cfg = self._pipeline_cfg.data
        return {
            "run_id": run_id,
            "generated_at": run_at.isoformat(),
            "force_include_all": force_include_all,
            "counts": {
                "preferred": artifacts.dataset.preferred.height,
                "background": artifacts.dataset.background.height,
                "scored": artifacts.result.scored.height,
                "recommended": artifacts.result.recommended.height,
            },
            "thresholds": {
                "high": predict_cfg.high_threshold,
                "boundary": predict_cfg.boundary_threshold,
                "sample_rate": predict_cfg.sample_rate,
                "last_n_days": predict_cfg.last_n_days,
                "start_date": predict_cfg.start_date,
                "end_date": predict_cfg.end_date,
            },
            "data_sources": {
                "categories": list(data_cfg.categories),
                "embedding_columns": list(data_cfg.embedding_columns),
                "preference_dir": data_cfg.preference_dir,
                "metadata_dir": data_cfg.metadata_dir,
                "embeddings_root": data_cfg.embeddings_root,
            },
        }
