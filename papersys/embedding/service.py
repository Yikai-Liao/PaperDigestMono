"""Minimal embedding service offering pure text-to-vector inference."""

from __future__ import annotations

import multiprocessing as mp
import os
import traceback
from pathlib import Path
from typing import Literal, Sequence, cast

import numpy as np
import torch
from loguru import logger
from multiprocessing.connection import Connection
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

from papersys.config.embedding import EmbeddingConfig, EmbeddingModelConfig


try:
    mp.set_start_method("spawn", force=True)
    logger.debug("Configured multiprocessing start method to 'spawn' at import time")
except RuntimeError as exc:
    logger.warning(
        "Failed to configure multiprocessing start method to 'spawn' at import time: {}",
        exc,
    )

os.environ.setdefault("VLLM_WORKER_MP_START_METHOD", "spawn")


def _vllm_embedding_worker(
    conn: Connection,
    model_payload: dict[str, str | int | float | None],
    texts: list[str],
    device: str,
    precision: Literal["float16", "float32"],
) -> None:
    """Spawned worker importing vLLM inside a separate process."""

    from loguru import logger as worker_logger

    result: dict[str, object] = {
        "status": "error",
        "error": "vLLM worker did not run",
        "traceback": "",
    }

    try:
        os.environ.setdefault("VLLM_WORKER_MP_START_METHOD", "spawn")
        if device:
            os.environ.setdefault("VLLM_DEVICE", device)
        try:
            from vllm import LLM  # Imported only inside worker process
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("vLLM is required but not installed") from exc

        model_name = cast(str, model_payload["name"])
        model_alias = cast(str, model_payload.get("alias") or model_name)

        worker_logger.info(
            "Worker loading vLLM model '{}' (alias: {}) on device {} with precision {}",
            model_name,
            model_alias,
            device,
            precision,
        )

        llm_kwargs: dict[str, Any] = {
            "model": model_name,
            "task": "embed",
            "enforce_eager": True,
            "trust_remote_code": True,
            "dtype": precision,
        }

        gpu_util = model_payload.get("vllm_gpu_memory_utilization")
        if isinstance(gpu_util, (int, float)):
            llm_kwargs["gpu_memory_utilization"] = float(gpu_util)

        llm = LLM(**llm_kwargs)

        outputs = llm.embed(texts)
        target_dtype = np.float16 if precision == "float16" else np.float32

        embeddings: list[list[float]] = []
        for output in outputs:
            outputs_list = cast(Sequence[object], output.outputs)
            if not outputs_list:
                raise RuntimeError("vLLM returned no embedding outputs")
            first_output = cast(object, outputs_list[0])
            vector = cast(Sequence[float], first_output.embedding)
            array = np.asarray(vector, dtype=target_dtype)
            embeddings.append(array.astype(target_dtype, copy=False).tolist())

        result = {"status": "ok", "embeddings": embeddings}
    except Exception as exc:  # pragma: no cover - propagated to parent process
        worker_logger.exception("vLLM worker failed: {}", exc)
        result = {
            "status": "error",
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        try:
            import gc

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()
            worker_logger.debug("vLLM worker GPU memory cleanup completed")
        except Exception as cleanup_exc:  # pragma: no cover
            worker_logger.warning("Failed to cleanup GPU memory: {}", cleanup_exc)

        try:
            conn.send(result)
        finally:
            conn.close()


class EmbeddingService:
    """Provide a minimal text embedding API."""

    def __init__(self, config: EmbeddingConfig, base_path: Path | None = None):
        self.config = config
        raw_output_dir = Path(config.output_dir)
        self.output_dir = self._resolve_output_dir(raw_output_dir, base_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._default_device: str | None = None

    def embed_texts(
        self,
        texts: Sequence[str],
        model_config: EmbeddingModelConfig,
    ) -> np.ndarray:
        """
        Generate embeddings for provided texts.

        Args:
            texts: Input sentences to embed.
            model_config: Model configuration controlling backend and batching.

        Returns:
            A 2D numpy array of shape (len(texts), model_config.dimension).
        """
        text_buffer = list(texts)
        if not text_buffer:
            return np.empty((0, model_config.dimension), dtype=np.float32)

        device = self._resolve_device(model_config)
        precision = self._resolve_precision(model_config, device)
        target_dtype = np.float16 if precision == "float16" else np.float32
        batch_size = self._resolve_batch_size(len(text_buffer), model_config)

        logger.info(
            "Embedding {} texts with model {} (backend={}, device={}, precision={}, batch_size={})",
            len(text_buffer),
            model_config.alias,
            model_config.backend,
            device,
            precision,
            batch_size,
        )

        batches: list[np.ndarray] = []
        progress = tqdm(
            total=len(text_buffer),
            desc=f"Embedding ({model_config.alias})",
            unit="text",
        )

        if model_config.backend == "sentence_transformer":
            model = self._load_sentence_transformer(model_config, device, precision)
            for start in range(0, len(text_buffer), batch_size):
                batch_texts = text_buffer[start : start + batch_size]
                vectors = self._encode_with_sentence_transformer(model, batch_texts, target_dtype)
                batches.append(vectors)
                progress.update(len(batch_texts))
        elif model_config.backend == "vllm":
            for start in range(0, len(text_buffer), batch_size):
                batch_texts = text_buffer[start : start + batch_size]
                vectors = self._embed_with_vllm_process(
                    batch_texts,
                    model_config,
                    device,
                    precision,
                )
                batches.append(np.asarray(vectors, dtype=target_dtype))
                progress.update(len(batch_texts))
        else:  # pragma: no cover - validated by config model
            progress.close()
            raise ValueError(f"Unsupported backend '{model_config.backend}'")

        progress.close()

        matrix = np.vstack(batches).astype(target_dtype, copy=False)
        if matrix.shape[1] != model_config.dimension:
            logger.warning(
                "Embedding dimension mismatch for model {}: expected={} actual={}",
                model_config.alias,
                model_config.dimension,
                matrix.shape[1],
            )
        return matrix

    def _embed_with_vllm_process(
        self,
        texts: list[str],
        model_config: EmbeddingModelConfig,
        device: str,
        precision: Literal["float16", "float32"],
    ) -> list[list[float]]:
        """Delegate vLLM inference to a dedicated subprocess."""

        ctx = mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)

        payload = model_config.model_dump(mode="python")
        process = ctx.Process(
            target=_vllm_embedding_worker,
            args=(child_conn, payload, texts, device, precision),
            name=f"vllm-embed-{model_config.alias}",
        )

        logger.debug(
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
            error = cast(str, message.get("error", "unknown error"))
            tb = cast(str, message.get("traceback", ""))
            raise RuntimeError(f"vLLM worker failed for model {model_config.alias}: {error}\n{tb}")

        embeddings = cast(list[list[float]], message.get("embeddings", []))
        logger.debug(
            "vLLM subprocess completed for model {} ({} embeddings)",
            model_config.alias,
            len(embeddings),
        )
        return embeddings

    def _load_sentence_transformer(
        self,
        model_config: EmbeddingModelConfig,
        device: str,
        precision: Literal["float16", "float32"],
    ) -> SentenceTransformer:
        """Instantiate a SentenceTransformer model with desired precision."""

        logger.debug(
            "Loading SentenceTransformer model {} (device={}, precision={})",
            model_config.name,
            device,
            precision,
        )
        model = SentenceTransformer(
            model_config.name,
            device=device,
            trust_remote_code=True,
        )
        if precision == "float16":
            try:
                model.half()
            except AttributeError:
                logger.warning(
                    "SentenceTransformer {} does not support half precision; falling back to float32",
                    model_config.alias,
                )
        return model

    @staticmethod
    def _encode_with_sentence_transformer(
        model: SentenceTransformer,
        texts: Sequence[str],
        target_dtype: np.dtype,
    ) -> np.ndarray:
        vectors = model.encode(
            list(texts),
            batch_size=len(texts),
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=target_dtype, copy=False)

    def _resolve_device(self, model_config: EmbeddingModelConfig) -> str:
        device = (model_config.device or "").strip()
        if device:
            return device
        if self._default_device is None:
            self._default_device = self._detect_device()
            logger.info("Detected embedding device: {}", self._default_device)
        return self._default_device

    def _resolve_precision(
        self,
        model_config: EmbeddingModelConfig,
        device: str,
    ) -> Literal["float16", "float32"]:
        configured = model_config.precision.lower()
        if configured == "auto":
            if device.startswith("cuda") or device.startswith("mps"):
                return "float16"
            return "float32"
        if configured not in {"float16", "float32"}:
            raise ValueError(f"Unsupported precision value: {model_config.precision}")
        return cast(Literal["float16", "float32"], configured)

    @staticmethod
    def _resolve_batch_size(total: int, model_config: EmbeddingModelConfig) -> int:
        """Infer batch size from config while avoiding empty slices."""

        configured = max(model_config.batch_size, 1)
        return min(configured, total)

    @staticmethod
    def _detect_device() -> str:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _resolve_output_dir(raw_path: Path, base_path: Path | None) -> Path:
        if raw_path.is_absolute():
            return raw_path
        if base_path is not None:
            return (base_path / raw_path).resolve()
        return (Path.cwd() / raw_path).resolve()


__all__ = ["EmbeddingService"]
