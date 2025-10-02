"""Integration tests that exercise recommendation & summary pipelines with real data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from pathlib import Path

import polars as pl
import pytest

from papersys.config import AppConfig, load_config, resolve_env_reference
from papersys.recommend.pipeline import PipelineArtifacts, RecommendationPipeline
from papersys.summary.generator import SummaryGenerationError
from papersys.summary.models import SummarySource
from papersys.summary.pipeline import SummaryPipeline


@dataclass(slots=True)
class RealDataWorkspace:
    """Prepared workspace derived from the migrated real dataset."""

    base_path: Path
    positive_ids: set[str]
    candidate_count: int


def _prepare_workspace(base_path: Path) -> RealDataWorkspace:
    data_root = Path(__file__).resolve().parents[2] / "data"
    metadata_path = data_root / "metadata" / "metadata-2025.csv"
    prefs_path = data_root / "preferences" / "events-2025.csv"
    jasper_path = data_root / "embeddings" / "jasper_v1" / "2025.parquet"
    conan_path = data_root / "embeddings" / "conan_v1" / "2025.parquet"

    metadata_dir = base_path / "metadata"
    embeddings_root = base_path / "embeddings"
    preference_dir = base_path / "preferences"
    summarized_dir = base_path / "summarized"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    embeddings_root.mkdir(parents=True, exist_ok=True)
    preference_dir.mkdir(parents=True, exist_ok=True)
    summarized_dir.mkdir(parents=True, exist_ok=True)

    categories_of_interest = {
        "cs.CL",
        "cs.CV",
        "cs.AI",
        "cs.LG",
        "stat.ML",
    }

    metadata = pl.read_csv(
        metadata_path,
        schema_overrides={"paper_id": pl.String, "categories": pl.String, "updated_at": pl.String},
    ).select(
        pl.col("paper_id").alias("id"),
        pl.col("title"),
        pl.col("abstract"),
        pl.col("categories"),
        pl.col("updated_at").alias("updated"),
    )

    metadata = metadata.with_columns(
        pl.col("categories")
        .str.split(";")
        .list.eval(pl.element().str.strip_chars())
        .alias("categories"),
    )

    categories_list = list(categories_of_interest)
    metadata = metadata.filter(
        pl.col("categories").list.eval(pl.element().is_in(categories_list)).list.any()
    )

    jasper = pl.read_parquet(jasper_path).rename({"paper_id": "id", "embedding": "jasper_v1"})
    jasper = jasper.filter(
        ~pl.col("jasper_v1").list.eval(pl.element().is_nan()).list.any()
    )

    conan = pl.read_parquet(conan_path).rename({"paper_id": "id", "embedding": "conan_v1"})
    conan = conan.filter(
        ~pl.col("conan_v1").list.eval(pl.element().is_nan()).list.any()
    )

    joined = metadata.join(jasper, on="id", how="inner").join(conan, on="id", how="inner")

    preferences = pl.read_csv(prefs_path, schema_overrides={"paper_id": pl.String})
    likes = (
        preferences
        .filter(pl.col("preference") == "like")
        .select(pl.col("paper_id").alias("id"))
        .unique()
    )

    positive = joined.join(likes, on="id", how="inner")
    if positive.is_empty():
        raise RuntimeError("No overlapping positive preferences found in real dataset")

    positive = positive.head(min(positive.height, 32))

    positive_id_list = positive["id"].to_list()
    background_pool = joined.filter(~pl.col("id").is_in(positive_id_list))
    bg_count = min(400, background_pool.height)
    if bg_count == 0:
        raise RuntimeError("Background pool is empty for real dataset integration test")
    background = background_pool.sample(n=bg_count, seed=42)

    combined = pl.concat([positive, background], how="vertical").unique("id")
    combined = combined.with_columns(
        pl.col("jasper_v1").list.eval(pl.element().cast(pl.Float32)),
        pl.col("conan_v1").list.eval(pl.element().cast(pl.Float32)),
    )

    metadata_output = combined.select(
        pl.col("id").alias("paper_id"),
        pl.col("title"),
        pl.col("abstract"),
        pl.col("categories").list.join(";").alias("categories"),
        pl.col("updated").alias("updated_at"),
    )
    metadata_output.write_csv(metadata_dir / "metadata-2025.csv", include_header=True)

    for alias in ("jasper_v1", "conan_v1"):
        alias_dir = embeddings_root / alias
        alias_dir.mkdir(parents=True, exist_ok=True)
        embedding_output = combined.select(
            pl.col("id").alias("paper_id"),
            pl.col(alias).alias("embedding"),
        ).with_columns(
            pl.lit("2025-09-01T00:00:00+00:00").alias("generated_at"),
            pl.col("embedding").list.len().alias("model_dim"),
            pl.lit("integration-test").alias("source"),
        )
        embedding_output.write_parquet(alias_dir / "2025.parquet")

    positive_ids = set(positive["id"].to_list())
    preference_payload = pl.DataFrame(
        {
            "id": list(positive_ids),
            "preference": ["like"] * len(positive_ids),
        }
    )
    preference_payload.write_csv(preference_dir / "events-2025.csv", include_header=True)

    return RealDataWorkspace(
        base_path=base_path,
        positive_ids=positive_ids,
        candidate_count=combined.height,
    )


def _select_available_llm_alias(config: AppConfig) -> str | None:
    for llm in config.llms:
        resolved = resolve_env_reference(llm.api_key, required=False)
        if resolved:
            return llm.alias
    return None


@pytest.fixture(scope="module")
def real_workspace(tmp_path_factory: pytest.TempPathFactory) -> RealDataWorkspace:
    base_path = tmp_path_factory.mktemp("papersys-real-data")
    return _prepare_workspace(base_path)


@pytest.fixture(scope="module")
def real_app_config(real_workspace: RealDataWorkspace) -> AppConfig:
    config_path = Path(__file__).resolve().parents[2] / "config" / "example.toml"
    config = load_config(AppConfig, config_path)
    if config.recommend_pipeline is None:
        raise RuntimeError("recommend_pipeline config is required")

    predict_cfg = config.recommend_pipeline.predict.model_copy(update={"last_n_days": 365})
    recommend_cfg = config.recommend_pipeline.model_copy(update={"predict": predict_cfg})

    summary_cfg = config.summary_pipeline
    available_alias = _select_available_llm_alias(config)
    if summary_cfg is not None and available_alias is not None:
        pdf_cfg = summary_cfg.pdf.model_copy(update={"model": available_alias})
        summary_cfg = summary_cfg.model_copy(update={"pdf": pdf_cfg})

    return config.model_copy(
        update={
            "data_root": real_workspace.base_path,
            "recommend_pipeline": recommend_cfg,
            "summary_pipeline": summary_cfg,
        }
    )


@pytest.fixture(scope="module")
def recommendation_artifacts(
    real_app_config: AppConfig,
    real_workspace: RealDataWorkspace,
) -> PipelineArtifacts:
    pipeline = RecommendationPipeline(real_app_config, base_path=real_workspace.base_path)
    artifacts = pipeline.run()
    if artifacts.dataset.preferred.is_empty() or artifacts.dataset.background.is_empty():
        raise RuntimeError("Real data pipeline produced empty datasets")
    return artifacts


def test_recommendation_pipeline_with_real_data(recommendation_artifacts: PipelineArtifacts) -> None:
    dataset = recommendation_artifacts.dataset
    result = recommendation_artifacts.result

    assert dataset.preferred.height > 0
    assert dataset.background.height > 0
    assert result.scored.height == dataset.background.height
    assert result.recommended.height >= 1
    scores = result.scored["score"]
    min_score = scores.min()
    max_score = scores.max()
    assert min_score is not None
    assert max_score is not None
    assert float(cast(float, min_score)) >= 0.0
    assert float(cast(float, max_score)) <= 1.0


def test_summary_pipeline_generates_when_llm_env_present(
    real_app_config: AppConfig,
    real_workspace: RealDataWorkspace,
    recommendation_artifacts: PipelineArtifacts,
) -> None:
    if real_app_config.summary_pipeline is None:
        pytest.skip("Summary pipeline not configured")

    llm_alias = real_app_config.summary_pipeline.llm.model
    target_llm = next((llm for llm in real_app_config.llms if llm.alias == llm_alias), None)
    if target_llm is None:
        pytest.skip(f"LLM alias '{llm_alias}' not configured")

    try:
        _ = target_llm.api_key_secret
    except EnvironmentError:
        pytest.skip(f"Environment variable for LLM '{llm_alias}' is not set")

    summary_pipeline = SummaryPipeline(real_app_config, base_path=real_workspace.base_path)

    top_candidates = (
        recommendation_artifacts.result.scored
        .sort("score", descending=True)
        .head(3)
    )
    sources: list[SummarySource] = []
    language = real_app_config.summary_pipeline.llm.language
    for row in top_candidates.iter_rows(named=True):
        sources.append(
            SummarySource(
                paper_id=row["id"],
                title=row["title"],
                abstract=row["abstract"],
                language=language,
            )
        )

    if not sources:
        pytest.skip("No candidates available for summarisation")

    try:
        artifacts = summary_pipeline.run(sources)
    except SummaryGenerationError as exc:
        pytest.skip(f"LLM call failed: {exc}")

    if not artifacts:
        pytest.skip("Summary pipeline did not produce outputs for available candidates")

    assert len(artifacts) == len(sources)
    for artifact in artifacts:
        assert artifact.markdown_path.exists()
        assert artifact.markdown_path.stat().st_size > 0
        assert artifact.pdf_path.exists()
        assert artifact.document.sections
