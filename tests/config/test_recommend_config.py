"""Unit tests for recommendation pipeline configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import RecommendPipelineConfig, load_config


def test_recommend_pipeline_config_minimal(tmp_path: Path) -> None:
    """Test loading a minimal but complete recommendation pipeline config."""
    config_file = tmp_path / "recommend.toml"
    config_file.write_text(
        """
        [data]
        embedding_columns = ["jasper_v1"]

        [predict]
        output_path = "./output.parquet"
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(RecommendPipelineConfig, config_file)

    # Check data config with defaults
    assert cfg.data.embedding_columns == ["jasper_v1"]
    assert cfg.data.preference_dir == "./preferences"
    assert cfg.data.metadata_dir == "./metadata"
    assert cfg.data.metadata_pattern == "metadata-*.csv"
    assert cfg.data.embeddings_root == "./embeddings"
    assert cfg.data.background_start_year == 2024
    assert len(cfg.data.categories) > 0  # Default categories

    # Check trainer with defaults
    assert cfg.trainer.seed == 42
    assert cfg.trainer.bg_sample_rate == 5.0
    assert cfg.trainer.logistic_regression.C == 1.0
    assert cfg.trainer.logistic_regression.max_iter == 1000

    # Check predict config
    assert cfg.predict.output_path == "./output.parquet"
    assert cfg.predict.last_n_days == 7


def test_recommend_pipeline_config_full(tmp_path: Path) -> None:
    """Test loading a fully specified recommendation pipeline config."""
    config_file = tmp_path / "recommend.toml"
    config_file.write_text(
        """
        [data]
        categories = ["cs.CL", "cs.LG"]
        embedding_columns = ["jasper_v1", "conan_v1"]
        preference_dir = "./pref"
    metadata_dir = "./meta"
    metadata_pattern = "sample-*.csv"
    embeddings_root = "./emb"
        background_start_year = 2023
        preference_start_year = 2022
        embed_repo_id = "test/embed"
        content_repo_id = "test/content"

        [trainer]
        seed = 99
        bg_sample_rate = 3.0

        [trainer.logistic_regression]
        C = 2.0
        max_iter = 500

        [predict]
        last_n_days = 14
        start_date = "2025-01-01"
        end_date = "2025-01-15"
        high_threshold = 0.9
        boundary_threshold = 0.7
        sample_rate = 0.002
        output_path = "./results.parquet"
        """.strip(),
        encoding="utf-8",
    )

    cfg = load_config(RecommendPipelineConfig, config_file)

    # Data config
    assert cfg.data.categories == ["cs.CL", "cs.LG"]
    assert cfg.data.embedding_columns == ["jasper_v1", "conan_v1"]
    assert cfg.data.preference_dir == "./pref"
    assert cfg.data.metadata_dir == "./meta"
    assert cfg.data.metadata_pattern == "sample-*.csv"
    assert cfg.data.embeddings_root == "./emb"
    assert cfg.data.background_start_year == 2023
    assert cfg.data.preference_start_year == 2022
    assert cfg.data.embed_repo_id == "test/embed"
    assert cfg.data.content_repo_id == "test/content"

    # Trainer config
    assert cfg.trainer.seed == 99
    assert cfg.trainer.bg_sample_rate == 3.0
    assert cfg.trainer.logistic_regression.C == 2.0
    assert cfg.trainer.logistic_regression.max_iter == 500

    # Predict config
    assert cfg.predict.last_n_days == 14
    assert cfg.predict.start_date == "2025-01-01"
    assert cfg.predict.end_date == "2025-01-15"
    assert cfg.predict.high_threshold == 0.9
    assert cfg.predict.boundary_threshold == 0.7
    assert cfg.predict.sample_rate == 0.002
    assert cfg.predict.output_path == "./results.parquet"


def test_recommend_pipeline_rejects_extra_fields(tmp_path: Path) -> None:
    """Ensure extra fields in nested config are rejected."""
    config_file = tmp_path / "recommend.toml"
    config_file.write_text(
        """
        [data]
        embedding_columns = ["jasper_v1"]
        unknown_field = "fail"

        [predict]
        output_path = "./output.parquet"
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(Exception):  # Pydantic ValidationError
        load_config(RecommendPipelineConfig, config_file)
