"""Service for generating and managing embeddings."""

from __future__ import annotations

import multiprocessing as mp
import os
import traceback
from pathlib import Path
from typing import Any, Literal, Sequence, cast

import numpy as np
import polars as pl
import torch
from loguru import logger
from sentence_transformers import SentenceTransformer

from papersys.config.embedding import EmbeddingConfig, EmbeddingModelConfig

from multiprocessing.connection import Connection


try:
    mp.set_start_method("spawn", force=True)
    logger.debug("Configured multiprocessing start method to 'spawn' at import time")
except RuntimeError as exc:
    logger.warning(
        "Failed to configure multiprocessing start method to 'spawn' at import time: {}",
        exc,
    )

os.environ.setdefault("VLLM_WORKER_MP_START_METHOD", "spawn")


_VLLM_BACKEND_SENTINEL: object = object()


def _vllm_embedding_worker(
    conn: Connection,
    model_payload: dict[str, Any],
    texts: list[str],
    device: str,
    precision: Literal["float16", "float32"],
) -> None:
    """Spawned worker that imports vLLM and generates embeddings."""

    from loguru import logger as worker_logger

    result: dict[str, Any] = {
        "status": "error",
        "error": "vLLM worker did not run",
        "traceback": "",
    }

    try:
        os.environ.setdefault("VLLM_WORKER_MP_START_METHOD", "spawn")

        try:
            from vllm import LLM  # Imported only inside worker process
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("vLLM is required but not installed") from exc

        model_name = model_payload["name"]
        model_alias = model_payload.get("alias", model_name)

        worker_logger.info(
            "Worker loading vLLM model '{}' (alias: {}) on device {} with precision {}",
            model_name,
            model_alias,
            device,
            precision,
        )

        llm = LLM(
            model=model_name,
            task="embed",
            enforce_eager=True,
            trust_remote_code=True,
            dtype=precision,
        )

        outputs = llm.embed(texts)
        target_dtype = np.float16 if precision == "float16" else np.float32

        embeddings: list[list[float]] = []
        for output in outputs:
            outputs_list = cast(Sequence[Any], output.outputs)
            if not outputs_list:
                raise RuntimeError("vLLM returned no embedding outputs")
            first_output = cast(Any, outputs_list[0])
            vector = first_output.embedding
            array = np.asarray(vector, dtype=target_dtype)
            embeddings.append(array.astype(target_dtype, copy=False).tolist())

        result = {"status": "ok", "embeddings": embeddings}
    except Exception as exc:  # pragma: no cover - logs propagated to parent
        worker_logger.exception("vLLM worker failed: {}", exc)
        result = {
            "status": "error",
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        try:
            conn.send(result)
        finally:
            conn.close()


class EmbeddingService:
    """Service for generating embeddings from paper metadata."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._default_device: str | None = None

    def _detect_device(self) -> str:
        """Auto-detect best available device."""
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"

    def _resolve_device(self, model_config: EmbeddingModelConfig) -> str:
        """Resolve the effective device for the given model configuration."""
        device = (model_config.device or "").strip()
        if device:
            return device

        if self._default_device is None:
            self._default_device = self._detect_device()
            logger.info("Using device: {}", self._default_device)

        return self._default_device

    def _resolve_precision(
        self,
        model_config: EmbeddingModelConfig,
        device: str,
    ) -> Literal["float16", "float32"]:
        """Resolve the effective precision for the given model configuration."""
        configured = model_config.precision.lower()

        if configured == "auto":
            if device.startswith("cuda") or device.startswith("mps"):
                return "float16"
            return "float32"

        if configured not in {"float16", "float32"}:
            raise ValueError(f"Unsupported precision value: {model_config.precision}")

        return configured  # type: ignore[return-value]

    def load_model(self, model_config: EmbeddingModelConfig) -> SentenceTransformer | object:
        """
        Load embedding model based on configuration.

        Args:
            model_config: Model configuration

        Returns:
            Loaded model (SentenceTransformer for native, vLLM for others)
        """
        device = self._resolve_device(model_config)
        precision = self._resolve_precision(model_config, device)
        logger.info(
            "Resolved device={} precision={} for model {}",
            device,
            precision,
            model_config.alias,
        )

        backend = model_config.backend

        if backend == "vllm":
            logger.info(
                "Delegating vLLM model '{}' (alias: {}) to subprocess worker",
                model_config.name,
                model_config.alias,
            )
            return _VLLM_BACKEND_SENTINEL

        if backend == "sentence_transformer":
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
            if precision == "float16":
                try:
                    model.half()
                    logger.info("Loaded model {} in float16 precision", model_config.alias)
                except AttributeError:
                    logger.warning(
                        "SentenceTransformer {} does not support half precision; falling back to float32",
                        model_config.alias,
                    )
            return model

        raise ValueError(f"Unsupported backend '{backend}' for model {model_config.alias}")

    def _embed_with_vllm_process(
        self,
        texts: list[str],
        model_config: EmbeddingModelConfig,
        device: str,
        precision: Literal["float16", "float32"],
    ) -> list[list[float]]:
        """Delegate embedding generation to a dedicated subprocess running vLLM."""

        ctx = mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)

        payload = model_config.model_dump(mode="python")
        process = ctx.Process(
            target=_vllm_embedding_worker,
            args=(child_conn, payload, texts, device, precision),
            name=f"vllm-embed-{model_config.alias}",
        )

        logger.info(
            "Starting vLLM subprocess for model {} with {} texts",
            model_config.alias,
            len(texts),
        )

        process.start()
        child_conn.close()

        try:
            message = parent_conn.recv()
        except EOFError as exc:
            raise RuntimeError("vLLM worker terminated before sending results") from exc
        finally:
            process.join()
            parent_conn.close()

        if process.exitcode not in (0, None):
            logger.error(
                "vLLM subprocess for model {} exited with code {}",
                model_config.alias,
                process.exitcode,
            )

        status = message.get("status")
        if status != "ok":
            error = message.get("error", "unknown error")
            tb = message.get("traceback", "")
            raise RuntimeError(
                f"vLLM worker failed for model {model_config.alias}: {error}\n{tb}"
            )

        embeddings = cast(list[list[float]], message.get("embeddings", []))
        logger.info(
            "vLLM subprocess completed for model {} ({} embeddings)",
            model_config.alias,
            len(embeddings),
        )
        return embeddings

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
        device = self._resolve_device(model_config)
        precision = self._resolve_precision(model_config, device)

        if isinstance(model, SentenceTransformer):
            # Use sentence-transformers
            embeddings = model.encode(
                texts,
                batch_size=model_config.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            target_dtype = np.float16 if precision == "float16" else np.float32
            embeddings_array = embeddings.astype(target_dtype, copy=False)
            result = embeddings_array.tolist()
            return cast(list[list[float]], result)

        if model is _VLLM_BACKEND_SENTINEL:
            return self._embed_with_vllm_process(texts, model_config, device, precision)

        raise TypeError(
            f"Unsupported embedding backend for model {model_config.alias}: {type(model)!r}"
        )

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
