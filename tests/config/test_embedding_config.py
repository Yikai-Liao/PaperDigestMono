"""Unit tests for embedding configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from papersys.config import AppConfig, EmbeddingConfig, EmbeddingModelConfig, load_config


def test_embedding_config_minimal(tmp_path: Path) -> None:
    """Test loading minimal embedding configuration."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [embedding]
        enabled = true
        output_dir = "embeddings"

        [[embedding.models]]
        alias = "test_model"
        name = "sentence-transformers/all-MiniLM-L6-v2"
        dimension = 384
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    assert app_config.embedding is not None
    assert app_config.embedding.enabled is True
    assert len(app_config.embedding.models) == 1
    model = app_config.embedding.models[0]
    assert model.alias == "test_model"
    assert model.dimension == 384
    assert model.batch_size == 32  # default


def test_embedding_config_multiple_models(tmp_path: Path) -> None:
    """Test loading multiple embedding models."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [embedding]
        enabled = true
        output_dir = "embeddings"
        auto_fill_backlog = true
        backlog_priority = "oldest_first"

        [[embedding.models]]
        alias = "model_a"
        name = "test/model-a"
        dimension = 128
        batch_size = 64
        device = "cuda"
        precision = "float16"

        [[embedding.models]]
        alias = "model_b"
        name = "test/model-b"
        dimension = 256
        max_length = 1024
        device = "cpu"
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    emb = app_config.embedding
    assert emb is not None
    assert emb.auto_fill_backlog is True
    assert emb.backlog_priority == "oldest_first"
    assert len(emb.models) == 2
    
    model_a = emb.models[0]
    assert model_a.alias == "model_a"
    assert model_a.batch_size == 64
    assert model_a.device == "cuda"
    assert model_a.precision == "float16"
    
    model_b = emb.models[1]
    assert model_b.alias == "model_b"
    assert model_b.max_length == 1024
    assert model_b.device == "cpu"
    assert model_b.precision == "float32"  # default


def test_embedding_config_with_hf_upload(tmp_path: Path) -> None:
    """Test embedding config with HF upload settings."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [embedding]
        enabled = true
        output_dir = "embeddings"
        upload_to_hf = true
        hf_repo_id = "user/repo"
        hf_token = "env:HF_TOKEN"

        [[embedding.models]]
        alias = "test"
        name = "test/model"
        dimension = 768
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    emb = app_config.embedding
    assert emb is not None
    assert emb.upload_to_hf is True
    assert emb.hf_repo_id == "user/repo"
    assert emb.hf_token == "env:HF_TOKEN"


def test_embedding_config_no_section(tmp_path: Path) -> None:
    """Test that missing embedding section results in None."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        data_root = "./data"
        """,
        encoding="utf-8",
    )

    app_config = load_config(AppConfig, config_path)
    assert app_config.embedding is None


def test_embedding_model_requires_dimension(tmp_path: Path) -> None:
    """Test that embedding model must specify dimension."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [embedding]
        enabled = true

        [[embedding.models]]
        alias = "test"
        name = "test/model"
        # Missing dimension field
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Field required"):
        load_config(AppConfig, config_path)


def test_embedding_config_rejects_extra_fields(tmp_path: Path) -> None:
    """Test that extra fields are rejected in embedding config."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [embedding]
        enabled = true
        output_dir = "embeddings"
        invalid_field = "fail"

        [[embedding.models]]
        alias = "test"
        name = "test/model"
        dimension = 384
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_config(AppConfig, config_path)
