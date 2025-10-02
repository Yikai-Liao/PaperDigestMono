"""Service for generating and managing embeddings."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import polars as pl
import torch
from loguru import logger
from sentence_transformers import SentenceTransformer

from papersys.config.embedding import EmbeddingConfig, EmbeddingModelConfig


class EmbeddingService:
    """Service for generating embeddings from paper metadata."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Auto-detect device
        self.device = self._detect_device()
        logger.info("Using device: {}", self.device)

    def _detect_device(self) -> str:
        """Auto-detect best available device."""
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"

    def load_model(self, model_config: EmbeddingModelConfig) -> SentenceTransformer | object:
        """
        Load embedding model based on configuration.

        Args:
            model_config: Model configuration

        Returns:
            Loaded model (SentenceTransformer for native, vLLM for others)
        """
        device = model_config.device or self.device
        
        # Determine model type: check if model requires vLLM (Qwen3-Embedding-0.6B)
        # jasper_v1 uses vLLM, but it's NOT qwen3 (it's a different slower model)
        requires_vllm = "Qwen3-Embedding" in model_config.name or "jasper" in model_config.alias.lower()
        
        if requires_vllm:
            # Use vLLM for large models that need custom inference
            logger.info(
                "Loading vLLM model: {} (alias: {})",
                model_config.name,
                model_config.alias,
            )
            return self._load_vllm_model(model_config, device)
        else:
            # Use sentence-transformers for native models (like conan_v1)
            logger.info(
                "Loading SentenceTransformer model: {} (alias: {})",
                model_config.name,
                model_config.alias,
            )
            model = SentenceTransformer(
                model_config.name,
                device=device,
                trust_remote_code=True,
            )
            return model

    def _load_vllm_model(self, model_config: EmbeddingModelConfig, device: str) -> object:
        """Load vLLM-based embedding model."""
        try:
            from vllm import LLM
        except ImportError as exc:
            logger.error("vLLM not installed; install with: uv add vllm")
            raise RuntimeError("vLLM required for this model") from exc

        # vLLM automatically handles device placement
        model = LLM(
            model=model_config.name,
            task="embed",
            enforce_eager=True,
            trust_remote_code=True,
        )
        return model

    def embed_batch(
        self,
        texts: list[str],
        model: SentenceTransformer | object,
        model_config: EmbeddingModelConfig,
    ) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings
            model: Loaded embedding model
            model_config: Model configuration

        Returns:
            List of embedding vectors
        """
        if isinstance(model, SentenceTransformer):
            # Use sentence-transformers
            embeddings = model.encode(
                texts,
                batch_size=model_config.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return embeddings.tolist()
        else:
            # Use vLLM
            outputs = model.embed(texts)
            return [output.outputs.embedding for output in outputs]

    def generate_embeddings_for_csv(
        self,
        csv_path: Path,
        model_config: EmbeddingModelConfig,
        limit: int | None = None,
    ) -> tuple[int, Path]:
        """
        Generate embeddings for papers in a CSV file.

        Args:
            csv_path: Path to input CSV file
            model_config: Model configuration
            limit: Maximum number of papers to process (for testing)

        Returns:
            Tuple of (number of embeddings generated, output parquet path)
        """
        logger.info("Processing {} with model {}", csv_path, model_config.alias)

        # Read CSV with explicit schema to preserve string types
        schema_overrides = {
            "paper_id": pl.String,
            "title": pl.String,
            "abstract": pl.String,
            "categories": pl.String,
            "primary_category": pl.String,
            "authors": pl.String,
        }
        df = pl.read_csv(csv_path, schema_overrides=schema_overrides)
        
        if limit:
            df = df.head(limit)
            logger.info("Limited to {} records for testing", limit)

        # Load model
        model = self.load_model(model_config)

        # Prepare texts (title + abstract)
        texts = []
        for row in df.iter_rows(named=True):
            title = row.get("title", "")
            abstract = row.get("abstract", "")
            text = f"{title}\n\n{abstract}".strip()
            texts.append(text)

        logger.info("Generating embeddings for {} texts...", len(texts))

        # Generate embeddings in batches
        embeddings = self.embed_batch(texts, model, model_config)

        logger.info("Generated {} embeddings", len(embeddings))

        # Create output dataframe
        result_df = pl.DataFrame({
            "paper_id": df["paper_id"],
            "embedding": embeddings,
        })

        # Determine output path
        year = csv_path.parent.name
        model_dir = self.output_dir / model_config.alias
        model_dir.mkdir(parents=True, exist_ok=True)
        output_path = model_dir / f"{year}.parquet"

        # Save to parquet
        result_df.write_parquet(output_path)
        logger.info("Saved embeddings to {}", output_path)

        return len(embeddings), output_path

    def detect_backlog(
        self,
        metadata_dir: Path,
        model_alias: str,
    ) -> list[Path]:
        """
        Detect CSV files without corresponding embeddings.

        Args:
            metadata_dir: Directory containing metadata CSV files
            model_alias: Model alias to check

        Returns:
            List of CSV paths that need embedding generation
        """
        model_dir = self.output_dir / model_alias
        existing_parquets = set()
        
        if model_dir.exists():
            for parquet_path in model_dir.glob("*.parquet"):
                # Extract year from filename (e.g., "2024.parquet" -> "2024")
                year = parquet_path.stem
                existing_parquets.add(year)

        # Find CSV files without embeddings
        backlog = []
        for year_dir in metadata_dir.iterdir():
            if not year_dir.is_dir():
                continue
            
            year = year_dir.name
            if year in existing_parquets:
                continue
            
            for csv_path in year_dir.glob("*.csv"):
                backlog.append(csv_path)

        logger.info(
            "Found {} CSV files in backlog for model {}",
            len(backlog),
            model_alias,
        )
        return backlog


__all__ = ["EmbeddingService"]
