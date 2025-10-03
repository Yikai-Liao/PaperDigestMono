"""Integration tests for the recommendation pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


DUMMY_PAPERS: list[dict[str, Any]] = [
    {
        "id": "p1",
        "title": "Positive example 1",
        "abstract": "...",
        "categories": ["cs.AI"],
        "updated": "2025-09-20",
        "embeddings": {
            "jasper_v1": [2.0, 2.0],
            "conan_v1": [2.1, 1.8],
        },
    },
    {
        "id": "p2",
        "title": "Positive example 2",
        "abstract": "...",
        "categories": ["cs.LG"],
        "updated": "2025-09-18",
        "embeddings": {
            "jasper_v1": [1.9, 2.2],
            "conan_v1": [1.8, 2.3],
        },
    },
    {
        "id": "p3",
        "title": "High scoring candidate",
        "abstract": "...",
        "categories": ["cs.AI"],
        "updated": "2025-09-21",
        "embeddings": {
            "jasper_v1": [1.5, 1.6],
            "conan_v1": [1.4, 1.7],
        },
    },
    {
        "id": "p4",
        "title": "Mid candidate",
        "abstract": "...",
        "categories": ["cs.AI"],
        "updated": "2023-09-16",
        "embeddings": {
            "jasper_v1": [0.4, 0.5],
            "conan_v1": [0.4, 0.5],
        },
    },
    {
        "id": "p5",
        "title": "Low candidate",
        "abstract": "...",
        "categories": ["math.ST"],
        "updated": "2025-09-22",
        "embeddings": {
            "jasper_v1": [0.1, 0.2],
            "conan_v1": [0.1, 0.2],
        },
    },
]


def write_dummy_preferences(tmpdir: Path, *, id_column: str = "id") -> None:
    (tmpdir / "prefs.csv").write_text(
        f"{id_column},preference\n"
        "p1,like\n"
        "p2,like\n",
        encoding="utf-8",
    )


def seed_metadata(metadata_dir: Path) -> None:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "paper_id": paper["id"],
            "title": paper["title"],
            "abstract": paper["abstract"],
            "categories": ";".join(paper["categories"]),
            "updated_at": paper["updated"],
        }
        for paper in DUMMY_PAPERS
    ]
    df = pl.DataFrame(rows)
    df.write_csv(metadata_dir / "metadata-2025.csv", include_header=True)


def seed_embeddings(embeddings_root: Path) -> None:
    for alias in {key for paper in DUMMY_PAPERS for key in paper["embeddings"].keys()}:
        alias_dir = embeddings_root / alias
        alias_dir.mkdir(parents=True, exist_ok=True)
        vectors = [
            {
                "paper_id": paper["id"],
                "embedding": [float(value) for value in paper["embeddings"][alias]],
                "generated_at": "2025-09-01T00:00:00+00:00",
                "model_dim": len(paper["embeddings"][alias]),
                "source": "unit-test",
            }
            for paper in DUMMY_PAPERS
        ]
        df = pl.DataFrame(
            {
                "paper_id": [item["paper_id"] for item in vectors],
                "embedding": [item["embedding"] for item in vectors],
                "generated_at": [item["generated_at"] for item in vectors],
                "model_dim": [item["model_dim"] for item in vectors],
                "source": [item["source"] for item in vectors],
            }
        )
        df.write_parquet(alias_dir / "2025.parquet")


def seed_test_data(data_root: Path) -> None:
    metadata_dir = data_root / "metadata"
    embeddings_root = data_root / "embeddings"
    seed_metadata(metadata_dir)
    seed_embeddings(embeddings_root)


@pytest.fixture()
def recommendation_config(tmp_path: Path) -> AppConfig:
    data_root = tmp_path / "data"
    preference_dir = data_root / "preferences"
    metadata_dir = data_root / "metadata"
    embeddings_root = data_root / "embeddings"
    summarized_dir = data_root / "summarized"
    for directory in (preference_dir, summarized_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_dummy_preferences(preference_dir)
    seed_test_data(data_root)

    recommend_cfg = RecommendPipelineConfig(
        data=DataConfig(
            categories=["cs.AI", "cs.LG"],
            embedding_columns=["jasper_v1", "conan_v1"],
            preference_dir=str(preference_dir.relative_to(data_root)),
            metadata_dir=str(metadata_dir.relative_to(data_root)),
            metadata_pattern="metadata-*.csv",
            embeddings_root=str(embeddings_root.relative_to(data_root)),
            background_start_year=2024,
            preference_start_year=2024,
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
        ingestion=None,
        embedding=None,
        recommend_pipeline=recommend_cfg,
        summary_pipeline=None,
        scheduler=None,
        backup=None,
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


def test_loader_accepts_paper_id_preferences(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    preference_dir = data_root / "preferences"
    metadata_dir = data_root / "metadata"
    embeddings_root = data_root / "embeddings"
    summarized_dir = data_root / "summarized"
    for directory in (preference_dir, summarized_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_dummy_preferences(preference_dir, id_column="paper_id")
    seed_test_data(data_root)

    recommend_cfg = RecommendPipelineConfig(
        data=DataConfig(
            categories=["cs.AI", "cs.LG"],
            embedding_columns=["jasper_v1", "conan_v1"],
            preference_dir=str(preference_dir.relative_to(data_root)),
            metadata_dir=str(metadata_dir.relative_to(data_root)),
            metadata_pattern="metadata-*.csv",
            embeddings_root=str(embeddings_root.relative_to(data_root)),
            background_start_year=2024,
            preference_start_year=2024,
        ),
        trainer=TrainerConfig(
            seed=42,
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

    config = AppConfig(
        data_root=data_root,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        ingestion=None,
        embedding=None,
        recommend_pipeline=recommend_cfg,
        summary_pipeline=None,
        scheduler=None,
        backup=None,
        llms=[],
    )

    loader = RecommendationDataLoader(config, base_path=data_root)
    dataset = loader.load()

    assert dataset.preferred.height == 2


def test_loader_filters_nan_embeddings(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    preference_dir = data_root / "preferences"
    metadata_dir = data_root / "metadata"
    embeddings_root = data_root / "embeddings"
    summarized_dir = data_root / "summarized"
    for directory in (preference_dir, summarized_dir):
        directory.mkdir(parents=True, exist_ok=True)

    write_dummy_preferences(preference_dir)
    seed_test_data(data_root)

    # Add an additional paper with NaN embeddings that should be filtered out
    metadata_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "paper_id": "p_nan",
                "title": "Paper with NaN embedding",
                "abstract": "...",
                "categories": "cs.AI",
                "updated_at": "2025-09-25",
            }
        ]
    ).write_csv(metadata_dir / "metadata-extra.csv")

    for alias in {key for paper in DUMMY_PAPERS for key in paper["embeddings"].keys()}:
        alias_dir = embeddings_root / alias
        alias_dir.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {
                "paper_id": ["p_nan"],
                "embedding": [[float("nan"), 0.0]],
                "generated_at": ["2025-09-01T00:00:00+00:00"],
                "model_dim": [2],
                "source": ["unit-test"],
            }
        ).write_parquet(alias_dir / "extra.parquet")

    recommend_cfg = RecommendPipelineConfig(
        data=DataConfig(
            categories=["cs.AI", "cs.LG"],
            embedding_columns=["jasper_v1", "conan_v1"],
            preference_dir=str(preference_dir.relative_to(data_root)),
            metadata_dir=str(metadata_dir.relative_to(data_root)),
            metadata_pattern="metadata-*.csv",
            embeddings_root=str(embeddings_root.relative_to(data_root)),
            background_start_year=2024,
            preference_start_year=2024,
        ),
        trainer=TrainerConfig(
            seed=42,
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

    config = AppConfig(
        data_root=data_root,
        scheduler_enabled=False,
        embedding_models=[],
        logging_level="INFO",
        ingestion=None,
        embedding=None,
        recommend_pipeline=recommend_cfg,
        summary_pipeline=None,
        scheduler=None,
        backup=None,
        llms=[],
    )

    loader = RecommendationDataLoader(config, base_path=data_root)
    dataset = loader.load()

    assert "p_nan" not in set(dataset.preferred["id"].to_list())
    assert "p_nan" not in set(dataset.background["id"].to_list())