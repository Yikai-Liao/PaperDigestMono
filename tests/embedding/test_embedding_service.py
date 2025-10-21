"""Unit tests for the refactored embedding service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from papersys.config.embedding import EmbeddingConfig, EmbeddingModelConfig
from papersys.embedding.service import EmbeddingService


@pytest.fixture
def embedding_config(tmp_path: Path) -> EmbeddingConfig:
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
                backend="sentence_transformer",
                model_path=None,
            )
        ],
        auto_fill_backlog=False,
        backlog_priority="recent_first",
        max_parallel_models=1,
        checkpoint_interval=1000,
        upload_to_hf=False,
        hf_repo_id=None,
        hf_token=None,
    )


@pytest.fixture
def service(embedding_config: EmbeddingConfig) -> EmbeddingService:
    return EmbeddingService(embedding_config)


def test_embed_texts_returns_matrix(service: EmbeddingService, embedding_config: EmbeddingConfig) -> None:
    texts = ["Paper title\n\nAbstract", "Second title\n\nAnother abstract"]
    model_config = embedding_config.models[0]
    fake_vectors = np.full((len(texts), model_config.dimension), 0.5, dtype=np.float32)

    mock_backend = MagicMock()
    mock_backend.embed_batch.return_value = fake_vectors

    with patch.object(service, "_get_backend", return_value=mock_backend):
        result = service.embed_texts(texts, model_config)

    assert result.shape == (len(texts), model_config.dimension)
    np.testing.assert_allclose(result, fake_vectors)
    mock_backend.embed_batch.assert_called_once()


def test_embed_texts_honours_batch_size(service: EmbeddingService, embedding_config: EmbeddingConfig) -> None:
    model_config = embedding_config.models[0].model_copy(update={"batch_size": 1})
    texts = ["t1", "t2", "t3"]
    fake_vector = np.ones((1, model_config.dimension), dtype=np.float32)

    mock_backend = MagicMock()
    mock_backend.embed_batch.return_value = fake_vector

    with patch.object(service, "_get_backend", return_value=mock_backend):
        result = service.embed_texts(texts, model_config)

    assert result.shape == (len(texts), model_config.dimension)
    assert mock_backend.embed_batch.call_count == len(texts)


def test_embed_texts_handles_empty_input(service: EmbeddingService, embedding_config: EmbeddingConfig) -> None:
    model_config = embedding_config.models[0]
    result = service.embed_texts([], model_config)
    assert result.shape == (0, model_config.dimension)


def test_embed_texts_vllm_backend(service: EmbeddingService) -> None:
    model_config = EmbeddingModelConfig(
        alias="qwen3_test",
        name="Qwen/Qwen3-Embedding-0.6B",
        dimension=1024,
        batch_size=2,
        max_length=512,
        device=None,
        precision="float32",
        backend="vllm",
        model_path=None,
    )

    fake_embeddings = np.array(
        [[0.1] * model_config.dimension, [0.2] * model_config.dimension],
        dtype=np.float32
    )
    
    mock_backend = MagicMock()
    mock_backend.embed_batch.return_value = fake_embeddings

    with patch.object(service, "_get_backend", return_value=mock_backend):
        result = service.embed_texts(["x", "y"], model_config)

    assert result.shape == (2, model_config.dimension)
    mock_backend.embed_batch.assert_called()


def test_batch_size_never_exceeds_total(service: EmbeddingService, embedding_config: EmbeddingConfig) -> None:
    model_config = embedding_config.models[0]
    assert service._resolve_batch_size(5, model_config) == 5


def test_backend_registry_has_all_backends() -> None:
    """Test that all expected backends are registered."""
    from papersys.embedding.service import BackendRegistry
    
    available = BackendRegistry.list_backends()
    assert "sentence_transformer" in available
    assert "vllm" in available


def test_backend_instances_are_cached(service: EmbeddingService) -> None:
    """Test that backend instances are cached and reused."""
    backend1 = service._get_backend("sentence_transformer")
    backend2 = service._get_backend("sentence_transformer")
    assert backend1 is backend2

