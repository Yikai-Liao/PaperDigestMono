"""Tests for embedding service."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import polars as pl
import pytest

from papersys.config.embedding import EmbeddingConfig, EmbeddingModelConfig
from papersys.embedding.service import EmbeddingService, _VLLM_BACKEND_SENTINEL


@pytest.fixture
def test_embedding_config(tmp_path: Path) -> EmbeddingConfig:
    """Create test embedding configuration."""
    return EmbeddingConfig(
        enabled=True,
        output_dir=str(tmp_path / "embeddings"),
        models=[
            EmbeddingModelConfig(
                alias="test_model",
                name="sentence-transformers/all-MiniLM-L6-v2",
                dimension=384,
                batch_size=32,
                max_length=512,
                device=None,
                precision="float32",
                model_path=None,
            )
        ],
        auto_fill_backlog=False,
        backlog_priority="oldest_first",
        max_parallel_models=1,
        checkpoint_interval=1000,
        upload_to_hf=False,
        hf_repo_id=None,
        hf_token=None,
    )


@pytest.fixture
def test_service(test_embedding_config: EmbeddingConfig) -> EmbeddingService:
    """Create test embedding service."""
    return EmbeddingService(test_embedding_config)


@pytest.fixture
def test_csv(tmp_path: Path) -> Path:
    """Create a test CSV file with paper metadata."""
    csv_path = tmp_path / "metadata" / "2024" / "test.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    df = pl.DataFrame({
        "paper_id": ["2024.00001", "2024.00002", "2024.00003"],
        "title": ["Paper 1", "Paper 2", "Paper 3"],
        "abstract": ["Abstract 1", "Abstract 2", "Abstract 3"],
        "categories": ["cs.AI", "cs.CL", "cs.CV"],
        "primary_category": ["cs.AI", "cs.CL", "cs.CV"],
        "authors": ["Author 1", "Author 2", "Author 3"],
        "published_at": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "updated_at": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "doi": ["", "", ""],
        "comment": ["", "", ""],
        "journal_ref": ["", "", ""],
    })
    df.write_csv(csv_path)
    
    return csv_path


def test_detect_device(test_service: EmbeddingService) -> None:
    """Test device detection."""
    device = test_service._detect_device()
    assert device in ["cuda", "mps", "cpu"]


def test_load_model_sentence_transformers(test_service: EmbeddingService, test_embedding_config: EmbeddingConfig) -> None:
    """Test loading a sentence-transformers model."""
    model_config = test_embedding_config.models[0]
    model = test_service.load_model(model_config)
    
    from sentence_transformers import SentenceTransformer
    assert isinstance(model, SentenceTransformer)


def test_load_model_vllm_backend_returns_sentinel(test_service: EmbeddingService) -> None:
    """Test that vLLM backend uses subprocess sentinel."""
    model_config = EmbeddingModelConfig(
        alias="qwen3_test",
        name="Qwen/Qwen3-Embedding-0.6B",
        dimension=768,
        batch_size=8,
        max_length=512,
        device=None,
        precision="auto",
        backend="vllm",
        model_path=None,
    )

    model = test_service.load_model(model_config)
    assert model is _VLLM_BACKEND_SENTINEL


def test_embed_batch(test_service: EmbeddingService, test_embedding_config: EmbeddingConfig) -> None:
    """Test embedding a batch of texts."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    
    model_config = test_embedding_config.models[0]
    
    # Create a real mock that passes isinstance check
    mock_model = Mock(spec=SentenceTransformer)
    mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384, [0.3] * 384])
    
    texts = ["Text 1", "Text 2", "Text 3"]
    embeddings = test_service.embed_batch(texts, mock_model, model_config)
    
    assert len(embeddings) == 3
    assert len(embeddings[0]) == 384
    mock_model.encode.assert_called_once()


def test_refresh_backlog_tracks_missing_rows(
    test_service: EmbeddingService,
    test_csv: Path,
    test_embedding_config: EmbeddingConfig,
) -> None:
    """Refreshing backlog should emit pending rows and update after embeddings exist."""

    metadata_dir = test_csv.parent.parent
    model_config = test_embedding_config.models[0]

    backlog_df = test_service.refresh_backlog(metadata_dir, model_config)
    assert backlog_df.height == 3
    assert backlog_df["missing_reason"].unique().to_list() == ["missing_embedding_file"]
    backlog_path = (test_service.output_dir / model_config.alias / "backlog.parquet")
    assert backlog_path.exists()

    model_dir = test_service.output_dir / model_config.alias
    model_dir.mkdir(parents=True, exist_ok=True)
    embedding_file = model_dir / "2024.parquet"
    vector = [0.1] * model_config.dimension
    embeddings = [vector, list(vector)]
    pl.DataFrame(
        {
            "paper_id": ["2024.00001", "2024.00002"],
            "embedding": embeddings,
            "generated_at": ["2025-01-01", "2025-01-01"],
            "model_dim": [model_config.dimension, model_config.dimension],
            "source": ["test", "test"],
        }
    ).with_columns(pl.col("model_dim").cast(pl.UInt32)).write_parquet(embedding_file)

    backlog_df = test_service.refresh_backlog(metadata_dir, model_config)
    assert backlog_df.height == 1
    assert backlog_df["paper_id"].to_list() == ["2024.00003"]
    assert backlog_df["missing_reason"].unique().to_list() == ["missing_embedding"]


def test_refresh_backlog_flat_structure(
    test_service: EmbeddingService,
    test_embedding_config: EmbeddingConfig,
    tmp_path: Path,
) -> None:
    """Backlog detection should support flat metadata-YYYY.csv layout."""

    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    csv_path = metadata_dir / "metadata-2024.csv"

    pl.DataFrame(
        {
            "paper_id": ["2024.00001"],
            "title": ["Paper"],
            "abstract": ["Abstract"],
            "categories": ["cs.AI"],
            "primary_category": ["cs.AI"],
            "authors": ["Author"],
            "published_at": ["2024-01-01"],
            "updated_at": ["2024-01-01"],
            "doi": [""],
            "comment": [""],
            "journal_ref": [""],
        }
    ).write_csv(csv_path)

    model_config = test_embedding_config.models[0]
    backlog_df = test_service.refresh_backlog(metadata_dir, model_config)

    assert backlog_df.height == 1
    assert backlog_df["origin"].to_list() == [str(csv_path)]


def test_generate_embeddings_for_csv_with_limit(
    test_service: EmbeddingService,
    test_csv: Path,
    test_embedding_config: EmbeddingConfig,
) -> None:
    """Test generating embeddings with a limit."""
    model_config = test_embedding_config.models[0]
    mock_model = object()
    mock_embeddings = [[0.1] * model_config.dimension, [0.2] * model_config.dimension]

    with patch.object(test_service, "load_model", return_value=mock_model) as load_mock, patch.object(
        test_service, "embed_batch", return_value=mock_embeddings
    ) as embed_mock:
        count, output_path = test_service.generate_embeddings_for_csv(
            test_csv,
            model_config,
            limit=2,
        )

    load_mock.assert_called_once()
    embed_mock.assert_called_once()

    assert count == 2
    assert output_path.exists()

    df = pl.read_parquet(output_path)
    assert df.height == 2
    assert df["paper_id"].to_list() == ["2024.00001", "2024.00002"]
    assert set(df.columns) >= {"embedding", "generated_at", "model_dim", "source"}
    assert df["source"].unique().to_list() == ["papersys.embedding.service"]
    assert df["model_dim"].unique().to_list() == [model_config.dimension]

    manifest_path = output_path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["model"] == model_config.alias
    assert manifest["dimension"] == model_config.dimension
    assert manifest["total_rows"] == 2
    assert manifest["years"] == {"2024": 2}


def test_generate_embeddings_is_idempotent(
    test_service: EmbeddingService,
    test_csv: Path,
    test_embedding_config: EmbeddingConfig,
) -> None:
    """Repeated generations should not duplicate embeddings."""

    model_config = test_embedding_config.models[0]
    mock_model = object()
    mock_embeddings = [[0.1] * model_config.dimension, [0.2] * model_config.dimension]

    with patch.object(test_service, "load_model", return_value=mock_model), patch.object(
        test_service, "embed_batch", return_value=mock_embeddings
    ):
        test_service.generate_embeddings_for_csv(test_csv, model_config, limit=2)
        test_service.generate_embeddings_for_csv(test_csv, model_config, limit=2)

    output_path = test_service.output_dir / model_config.alias / "2024.parquet"
    df = pl.read_parquet(output_path)
    assert df.height == 2
