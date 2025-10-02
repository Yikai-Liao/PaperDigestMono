#!/usr/bin/env python3
"""Run a quick embedding pass for a configured model.

This helper script mirrors the inline snippet we've been using for manual tests,
while ensuring the usual Python multiprocessing guard is in place so CUDA/vLLM
can safely spawn worker processes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from papersys.config import AppConfig, load_config
from papersys.embedding.service import EmbeddingService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/example.toml"),
        help="Path to the runtime configuration file.",
    )
    parser.add_argument(
        "--model-alias",
        type=str,
        default="qwen3_v1",
        help="Embedding model alias to load from config.",
    )
    parser.add_argument(
        "--text",
        type=str,
        default="Test text for Qwen3 embedding",
        help="Sample text to embed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    cfg = load_config(AppConfig, args.config)
    if cfg.embedding is None:
        raise SystemExit("Embedding config missing")

    service = EmbeddingService(cfg.embedding)
    try:
        model_cfg = next(
            model for model in cfg.embedding.models if model.alias == args.model_alias
        )
    except StopIteration as exc:  # pragma: no cover - guard for manual usage
        known = ", ".join(model.alias for model in cfg.embedding.models)
        raise SystemExit(
            f"Embedding model alias '{args.model_alias}' not found. Known aliases: {known}"
        ) from exc

    model = service.load_model(model_cfg)
    embeddings = service.embed_batch([args.text], model, model_cfg)
    vector = embeddings[0]
    print({"embedding_len": len(vector), "first_values": vector[:5]})


if __name__ == "__main__":
    main()
