"""Tests for embedding service."""

from __future__ import annotations

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


def test_detect_backlog(test_service: EmbeddingService, test_csv: Path, tmp_path: Path) -> None:
    """Test detecting CSV files without embeddings."""
    metadata_dir = test_csv.parent.parent
    model_alias = "test_model"
    
    # Initially, no embeddings exist
    backlog = test_service.detect_backlog(metadata_dir, model_alias)
    assert len(backlog) == 1
    assert backlog[0] == test_csv
    
    # Create embedding file
    model_dir = test_service.output_dir / model_alias
    model_dir.mkdir(parents=True, exist_ok=True)
    embedding_file = model_dir / "2024.parquet"
    
    df = pl.DataFrame({
        "paper_id": ["2024.00001"],
        "embedding": [[[0.1] * 384]],
    })
    df.write_parquet(embedding_file)
    
    # Now backlog should be empty
    backlog = test_service.detect_backlog(metadata_dir, model_alias)
    assert len(backlog) == 0


def test_generate_embeddings_for_csv_with_limit(
    test_service: EmbeddingService,
    test_csv: Path,
    test_embedding_config: EmbeddingConfig,
) -> None:
    """Test generating embeddings with a limit."""
    model_config = test_embedding_config.models[0]
    
    # Generate embeddings with limit=2
    count, output_path = test_service.generate_embeddings_for_csv(
        test_csv,
        model_config,
        limit=2,
    )
    
    assert count == 2
    assert output_path.exists()
    
    # Verify output
    df = pl.read_parquet(output_path)
    assert len(df) == 2
    assert "paper_id" in df.columns
    assert "embedding" in df.columns
    assert df["paper_id"].to_list() == ["2024.00001", "2024.00002"]
