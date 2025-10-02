"""Configuration models for embedding generation and backfill."""

from __future__ import annotations

from pydantic import Field

from .base import BaseConfig


class EmbeddingModelConfig(BaseConfig):
    """Configuration for a single embedding model."""

    alias: str = Field(..., description="Model alias (e.g., 'jasper_v1')")
    name: str = Field(..., description="Model name or HuggingFace ID")
    dimension: int = Field(..., description="Embedding vector dimension", ge=1)
    batch_size: int = Field(32, description="Inference batch size", ge=1)
    max_length: int = Field(512, description="Maximum sequence length for tokenization", ge=1)
    device: str | None = Field(
        None,
        description="Device override: 'cuda', 'mps', 'cpu', or None for auto-detect"
    )
    precision: str = Field("float32", description="Output precision: 'float32' or 'float16'")
    model_path: str | None = Field(None, description="Local path to model weights (optional)")


class EmbeddingConfig(BaseConfig):
    """Configuration for embedding generation pipeline."""

    enabled: bool = Field(True, description="Whether embedding pipeline is enabled")
    output_dir: str = Field("embeddings", description="Base directory for embedding storage")
    
    models: list[EmbeddingModelConfig] = Field(
        default_factory=list,
        description="List of embedding models to use"
    )
    
    # Backfill settings
    auto_fill_backlog: bool = Field(
        True,
        description="Automatically generate backlog for new models on startup"
    )
    backlog_priority: str = Field(
        "recent_first",
        description="Backlog processing order: 'recent_first', 'oldest_first', 'random'"
    )
    
    # Resource limits
    max_parallel_models: int = Field(1, description="Max models to run in parallel", ge=1)
    checkpoint_interval: int = Field(1000, description="Save checkpoint every N papers", ge=1)
    
    # Upload settings
    upload_to_hf: bool = Field(False, description="Upload embeddings to Hugging Face after generation")
    hf_repo_id: str | None = Field(None, description="Hugging Face dataset repo ID")
    hf_token: str | None = Field(None, description="HF token (supports 'env:VAR_NAME' format)")


__all__ = ["EmbeddingConfig", "EmbeddingModelConfig"]
