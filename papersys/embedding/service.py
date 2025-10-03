"""Service for generating and managing embeddings."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import traceback
from datetime import datetime, timezone
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
_EMBEDDING_SOURCE = "papersys.embedding.service"
_BACKLOG_SCHEMA = {
    "paper_id": pl.String,
    "missing_reason": pl.String,
    "origin": pl.String,
    "queued_at": pl.String,
    "model_alias": pl.String,
    "year": pl.String,
}
_METADATA_SCHEMA = {
    "paper_id": pl.String,
    "title": pl.String,
    "abstract": pl.String,
    "categories": pl.String,
    "primary_category": pl.String,
    "authors": pl.String,
}


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

    def _model_dir(self, model_alias: str) -> Path:
        model_dir = self.output_dir / model_alias
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir

    def _manifest_path(self, model_alias: str) -> Path:
        return self._model_dir(model_alias) / "manifest.json"

    def _backlog_path(self, model_alias: str) -> Path:
        return self._model_dir(model_alias) / "backlog.parquet"

    def _metadata_candidates(self, metadata_dir: Path) -> list[Path]:
        if not metadata_dir.exists():
            logger.warning("Metadata directory {} does not exist", metadata_dir)
            return []

        flat_files = [
            path
            for path in metadata_dir.glob("metadata-*.csv")
            if path.is_file()
        ]
        if flat_files:
            return sorted(flat_files)

        nested_files: list[Path] = []
        for year_dir in sorted(metadata_dir.iterdir()):
            if year_dir.is_dir():
                nested_files.extend(sorted(year_dir.glob("*.csv")))
        return nested_files

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
        df = pl.read_csv(csv_path, schema_overrides=_METADATA_SCHEMA)

        if limit is not None:
            df = df.head(limit)
            logger.info("Limited to {} records for testing", limit)

        if df.is_empty():
            logger.warning("No rows found in {}; skipping embedding generation", csv_path)
            year = self._infer_year_from_path(csv_path)
            if year is None:
                raise ValueError(f"Unable to infer year from CSV path: {csv_path}")
            output_path = self._model_dir(model_config.alias) / f"{year}.parquet"
            if output_path.exists():
                self._update_manifest(model_config.alias, model_config.dimension)
            return 0, output_path

        model = self.load_model(model_config)

        texts: list[str] = []
        for row in df.iter_rows(named=True):
            title = row.get("title", "") or ""
            abstract = row.get("abstract", "") or ""
            text = f"{title}\n\n{abstract}".strip()
            texts.append(text)

        if not texts:
            logger.warning("No texts prepared for embedding from {}; skipping", csv_path)
            year = self._infer_year_from_path(csv_path)
            if year is None:
                raise ValueError(f"Unable to infer year from CSV path: {csv_path}")
            output_path = self._model_dir(model_config.alias) / f"{year}.parquet"
            if output_path.exists():
                self._update_manifest(model_config.alias, model_config.dimension)
            return 0, output_path

        logger.info("Generating embeddings for {} texts...", len(texts))
        embeddings = self.embed_batch(texts, model, model_config)
        logger.info("Generated {} embeddings", len(embeddings))

        timestamp = datetime.now(timezone.utc).isoformat()
        model_dir = self._model_dir(model_config.alias)
        year = self._infer_year_from_path(csv_path)
        if year is None:
            raise ValueError(f"Unable to infer year from CSV path: {csv_path}")
        output_path = model_dir / f"{year}.parquet"

        result_df = pl.DataFrame(
            {
                "paper_id": df["paper_id"],
                "embedding": embeddings,
                "generated_at": [timestamp] * len(embeddings),
                "model_dim": [model_config.dimension] * len(embeddings),
                "source": [_EMBEDDING_SOURCE] * len(embeddings),
            }
        ).with_columns(pl.col("model_dim").cast(pl.UInt32))

        if output_path.exists():
            existing = pl.read_parquet(output_path)
            combined = pl.concat([existing, result_df], how="vertical_relaxed")
        else:
            combined = result_df

        combined = self._deduplicate_embeddings(combined)
        combined.write_parquet(output_path)
        logger.info("Saved embeddings to {} ({} rows)", output_path, combined.height)

        self._update_manifest(model_config.alias, model_config.dimension)

        return len(result_df), output_path

    def refresh_backlog(
        self,
        metadata_dir: Path,
        model_config: EmbeddingModelConfig,
    ) -> pl.DataFrame:
        """Refresh backlog entries for the given model and return the current dataset."""

        model_dir = self._model_dir(model_config.alias)
        timestamp = datetime.now(timezone.utc).isoformat()
        backlog_entries: list[pl.DataFrame] = []

        csv_candidates = self._metadata_candidates(metadata_dir)
        if not csv_candidates:
            logger.info("No metadata files found under {}", metadata_dir)

        for csv_path in csv_candidates:
            year = self._infer_year_from_path(csv_path)
            if year is None:
                logger.warning("Skipping metadata file without detectable year: {}", csv_path)
                continue

            metadata_lazy = pl.scan_csv(
                csv_path,
                schema_overrides={"paper_id": pl.String},
            ).select("paper_id")
            parquet_path = model_dir / f"{year}.parquet"

            if parquet_path.exists():
                embeddings_lazy = pl.scan_parquet(parquet_path).select("paper_id")
                missing_lazy = metadata_lazy.join(embeddings_lazy, on="paper_id", how="anti")
                missing_df = missing_lazy.collect()
                missing_reason = "missing_embedding"
            else:
                missing_df = metadata_lazy.collect()
                missing_reason = "missing_embedding_file"

            if missing_df.is_empty():
                continue

            backlog_entries.append(
                missing_df.with_columns(
                    pl.lit(missing_reason).alias("missing_reason"),
                    pl.lit(str(csv_path)).alias("origin"),
                    pl.lit(timestamp).alias("queued_at"),
                    pl.lit(model_config.alias).alias("model_alias"),
                    pl.lit(str(year)).alias("year"),
                )
            )

        backlog_path = self._backlog_path(model_config.alias)

        if backlog_entries:
            backlog_df = pl.concat(backlog_entries, how="vertical_relaxed")
            backlog_df = backlog_df.unique(subset=["model_alias", "paper_id"], keep="first")
            backlog_df.select(list(_BACKLOG_SCHEMA.keys())).write_parquet(backlog_path)
            logger.info(
                "Backlog refreshed for model {}: {} pending items",
                model_config.alias,
                backlog_df.height,
            )
            return backlog_df.select(list(_BACKLOG_SCHEMA.keys()))

        if backlog_path.exists():
            backlog_path.unlink()
            logger.info("No backlog remaining for model {}; removed {}", model_config.alias, backlog_path)

        empty_df = pl.DataFrame({name: [] for name in _BACKLOG_SCHEMA}, schema=_BACKLOG_SCHEMA)
        return empty_df

    def detect_backlog(
        self,
        metadata_dir: Path,
        model_config: EmbeddingModelConfig,
    ) -> pl.DataFrame:
        """Alias for refresh_backlog kept for backward compatibility."""

        return self.refresh_backlog(metadata_dir, model_config)

    def _deduplicate_embeddings(self, frame: pl.DataFrame) -> pl.DataFrame:
        if frame.is_empty():
            return frame

        if "generated_at" in frame.columns:
            sorted_frame = frame.sort(
                ["paper_id", "generated_at"],
                descending=[False, True],
            )
        else:
            sorted_frame = frame.sort("paper_id")

        deduped = sorted_frame.unique(subset=["paper_id"], keep="first")
        desired_order = [
            "paper_id",
            "embedding",
            "generated_at",
            "model_dim",
            "source",
        ]
        columns = [col for col in desired_order if col in deduped.columns]
        columns += [col for col in deduped.columns if col not in columns]
        return deduped.select(columns)

    def _update_manifest(self, model_alias: str, dimension: int) -> None:
        model_dir = self._model_dir(model_alias)
        manifest_path = self._manifest_path(model_alias)

        year_counts: dict[str, int] = {}
        total_rows = 0
        parquet_files = sorted(
            path
            for path in model_dir.glob("*.parquet")
            if path.name != "backlog.parquet"
        )

        for parquet_path in parquet_files:
            year = parquet_path.stem
            count = int(pl.scan_parquet(parquet_path).select(pl.len()).collect().item())
            year_counts[year] = count
            total_rows += count

        manifest = {
            "model": model_alias,
            "dimension": dimension,
            "total_rows": total_rows,
            "years": year_counts,
            "files": [path.name for path in parquet_files],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": _EMBEDDING_SOURCE,
        }

        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        logger.debug("Updated manifest {}", manifest_path)

    @staticmethod
    def _infer_year_from_path(csv_path: Path) -> str | None:
        """Try to infer the year string from either the parent directory or filename."""
        parent_name = csv_path.parent.name
        if parent_name.isdigit() and len(parent_name) == 4:
            return parent_name

        stem = csv_path.stem
        for token in stem.replace("_", "-").split("-"):
            if token.isdigit() and len(token) == 4:
                return token

        return None


__all__ = ["EmbeddingService"]
