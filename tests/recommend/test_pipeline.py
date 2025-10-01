"""Integration tests for the recommendation pipeline."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from papersys.config import (
    AppConfig,
    DataConfig,
    LogisticRegressionConfig,
    PredictConfig,
    RecommendPipelineConfig,
    TrainerConfig,
)
from papersys.recommend.data import RecommendationDataLoader
from papersys.recommend.pipeline import PipelineArtifacts, RecommendationPipeline
from papersys.recommend.predictor import PredictionResult, RecommendationPredictor
from papersys.recommend.trainer import RecommendationTrainer


def write_dummy_preferences(tmpdir: Path) -> None:
    (tmpdir / "prefs.csv").write_text(
        "id,preference\n"
        "p1,like\n"
        "p2,like\n",
        encoding="utf-8",
    )


def write_dummy_candidates(tmpdir: Path) -> None:
    rows = [
        {
            "id": "p1",
            "title": "Positive example 1",
            "abstract": "...",
            "categories": ["cs.AI"],
            "updated": "2025-09-20",
            "jasper_v1": [2.0, 2.0],
            "conan_v1": [2.1, 1.8],
        },
        {
            "id": "p2",
            "title": "Positive example 2",
            "abstract": "...",
            "categories": ["cs.LG"],
            "updated": "2025-09-18",
            "jasper_v1": [1.9, 2.2],
            "conan_v1": [1.8, 2.3],
        },
        {
            "id": "p3",
            "title": "High scoring candidate",
            "abstract": "...",
            "categories": ["cs.AI"],
            "updated": "2025-09-21",
            "jasper_v1": [1.5, 1.6],
            "conan_v1": [1.4, 1.7],
        },
        {
            "id": "p4",
            "title": "Mid candidate",
            "abstract": "...",
            "categories": ["cs.AI"],
            "updated": "2023-09-16",
            "jasper_v1": [0.4, 0.5],
            "conan_v1": [0.4, 0.5],
        },
        {
            "id": "p5",
            "title": "Low candidate",
            "abstract": "...",
            "categories": ["math.ST"],
            "updated": "2025-09-22",
            "jasper_v1": [0.1, 0.2],
            "conan_v1": [0.1, 0.2],
        },
    ]
    df = pl.DataFrame(
        rows,
        schema={
            "id": pl.String,
            "title": pl.String,
            "abstract": pl.String,
            "categories": pl.List(pl.String),
            "updated": pl.String,
            "jasper_v1": pl.List(pl.Float64),
            "conan_v1": pl.List(pl.Float64),
        },
    )
    df.write_parquet(tmpdir / "2025.parquet")


@pytest.fixture()
def recommendation_config(tmp_path: Path) -> AppConfig:
    data_root = tmp_path / "data"
    preference_dir = data_root / "preference"
    cache_dir = data_root / "cache"
    summarized_dir = data_root / "summarized"
    for directory in (preference_dir, cache_dir, summarized_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_dummy_preferences(preference_dir)
    write_dummy_candidates(cache_dir)

    recommend_cfg = RecommendPipelineConfig(
        data=DataConfig(
            categories=["cs.AI", "cs.LG"],
            embedding_columns=["jasper_v1", "conan_v1"],
            preference_dir=str(preference_dir.relative_to(data_root)),
            cache_dir=str(cache_dir.relative_to(data_root)),
            background_start_year=2024,
            preference_start_year=2024,
            embed_repo_id="local/embeddings",
            content_repo_id="local/content",
        ),
        trainer=TrainerConfig(
            seed=123,
            bg_sample_rate=2.0,
            logistic_regression=LogisticRegressionConfig(C=1.0, max_iter=200),
        ),
        predict=PredictConfig(
            last_n_days=30,
            high_threshold=0.8,
            boundary_threshold=0.6,
            sample_rate=0.5,
            output_path="predictions.parquet",
            start_date="",
            end_date="",
        ),
    )

    return AppConfig(
        data_root=data_root,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        recommend_pipeline=recommend_cfg,
        summary_pipeline=None,
        llms=[],
    )


def test_loader_filters_categories_and_year(recommendation_config: AppConfig) -> None:
    loader = RecommendationDataLoader(recommendation_config, base_path=recommendation_config.data_root)
    sources = loader.describe_sources()
    assert sources.missing() == ()

    dataset = loader.load()

    assert dataset.preferred.height == 2
    assert dataset.background.height == 1  # p5 filtered by categories, p4 by year
    assert {"p1", "p2"} == set(dataset.preferred["id"].to_list())
    assert set(dataset.background["id"].to_list()) == {"p3"}


def test_trainer_and_predictor_outputs(recommendation_config: AppConfig) -> None:
    loader = RecommendationDataLoader(recommendation_config, base_path=recommendation_config.data_root)
    dataset = loader.load()

    trainer = RecommendationTrainer(recommendation_config)
    model = trainer.train(dataset)

    predictor = RecommendationPredictor(recommendation_config)
    result = predictor.predict(model, dataset.background)

    assert isinstance(result, PredictionResult)
    assert result.scored.height == dataset.background.height
    assert result.recommended.height >= 1
    assert {"score", "show"}.issubset(result.scored.columns)


def test_pipeline_full_run(recommendation_config: AppConfig) -> None:
    pipeline = RecommendationPipeline(recommendation_config, base_path=recommendation_config.data_root)
    artifacts = pipeline.run()

    assert isinstance(artifacts, PipelineArtifacts)
    assert not artifacts.dataset.preferred.is_empty()
    assert not artifacts.dataset.background.is_empty()
    assert artifacts.result.recommended.height >= 1