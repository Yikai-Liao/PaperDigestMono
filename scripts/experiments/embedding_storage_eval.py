"""Benchmark Parquet vs Zarr(SQLiteStore) embedding storage layouts.

This script copies real embedding data into `tmp/embedding_storage_eval/`
and evaluates:
    * Sequential append throughput (chunked writes)
    * Resulting file sizes and compression ratios
    * Random indexed batch reads

The benchmark intentionally ignores extra metadata columns and only persists
`paper_id` and the embedding vectors, aligning with the target minimal schema.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import duckdb
import numpy as np
import polars as pl
import zarr
import zfpy
from loguru import logger
from numpy.typing import NDArray
from zarr.storage import SQLiteStore
from numcodecs.zfpy import ZFPY
import pyarrow as pa
import pyarrow.parquet as pq


@dataclass(slots=True)
class AppendStats:
    total_seconds: float
    mean_seconds: float
    median_seconds: float
    samples: int


@dataclass(slots=True)
class RandomReadStats:
    total_seconds: float
    mean_seconds: float
    median_seconds: float
    batches: int
    batch_size: int


@dataclass(slots=True)
class BenchmarkReport:
    source_parquet: str
    source_rows: int
    embedding_dim: int
    parquet_float16_path: str
    parquet_float16_size: int
    parquet_float16_random_read: RandomReadStats
    npz_path: str
    npz_size: int
    npz_load_seconds: float
    npz_random_read: RandomReadStats
    zarr_sqlite_path: str
    zarr_sqlite_size: int
    zarr_append: AppendStats
    zarr_random_read: RandomReadStats
    compression_ratio_vs_parquet: float
    compression_ratio_vs_npz: float
    zfpy_lossless: "ZFPStats | None"
    zfpy_lossy: "ZFPStats | None"


@dataclass(slots=True)
class ZFPStats:
    path: str
    size: int
    compress_seconds: float
    load_seconds: float
    decompress_seconds: float
    random_read: RandomReadStats
    mode: str
    parameter: float | int | None


def _chunk_indices(total: int, chunk_size: int) -> Iterable[tuple[int, int]]:
    for start in range(0, total, chunk_size):
        end = min(start + chunk_size, total)
        yield start, end


def _load_embeddings(
    parquet_path: Path,
    max_rows: int | None,
    target_dim: int | None,
) -> tuple[list[str], NDArray[np.float32], int]:
    scan = pl.scan_parquet(str(parquet_path)).select(["paper_id", "embedding"])
    if max_rows is not None:
        scan = scan.head(max_rows)
    frame = scan.collect()
    if frame.is_empty():
        raise ValueError(f"No rows collected from {parquet_path}")
    id_column = frame["paper_id"].to_list()
    embedding_lists = frame["embedding"].to_list()
    lengths = [len(vec) for vec in embedding_lists]
    if target_dim is None:
        from collections import Counter

        counter = Counter(lengths)
        target_dim = counter.most_common(1)[0][0]
    filtered_ids: list[str] = []
    filtered_vectors: list[list[float]] = []
    dropped = 0
    for pid, vec, length in zip(id_column, embedding_lists, lengths):
        if length != target_dim:
            dropped += 1
            continue
        filtered_ids.append(pid)
        filtered_vectors.append(vec)
    if dropped:
        logger.warning("Dropped {} rows that do not match target dimension {}", dropped, target_dim)
    if not filtered_ids:
        raise ValueError("All rows were dropped due to inconsistent embedding dimensions")
    vectors = np.asarray(filtered_vectors, dtype=np.float32)
    logger.info("Loaded {} embeddings from {} (dimension={})", len(filtered_ids), parquet_path, vectors.shape[1])
    return filtered_ids, vectors, target_dim


def _write_float16_parquet(
    ids: Sequence[str],
    vectors: NDArray[np.float32],
    output_path: Path,
) -> float:
    vectors16 = vectors.astype(np.float16, copy=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    id_array = pa.array(ids, type=pa.string())
    flat = pa.array(vectors16.reshape(-1), type=pa.float16())
    embedding_array = pa.FixedSizeListArray.from_arrays(flat, vectors16.shape[1])
    table = pa.Table.from_arrays([id_array, embedding_array], names=["paper_id", "embedding"])

    start = time.perf_counter()
    pq.write_table(
        table,
        output_path,
        compression="zstd",
        compression_level=5,
    )
    duration = time.perf_counter() - start
    logger.info("Wrote float16 parquet to {} in {:.2f}s (rows={})", output_path, duration, len(ids))
    return duration


def _prepare_sqlite_store(path: Path) -> SQLiteStore:
    if path.exists():
        path.unlink()
    journal = path.with_suffix(path.suffix + "-journal")
    wal = path.with_suffix(path.suffix + "-wal")
    for extra in (journal, wal):
        if extra.exists():
            extra.unlink()
    return SQLiteStore(str(path))


def _write_zarr_sqlite(
    ids: Sequence[str],
    vectors: NDArray[np.float32],
    *,
    chunk_size: int,
    compressor_name: str,
    clevel: int,
    store_path: Path,
    zfpy_params: dict[str, object] | None,
) -> tuple[AppendStats, Path]:
    if zfpy_params is None:
        vectors_store = vectors.astype(np.float16)
    else:
        vectors_store = vectors.astype(np.float32)
    store = _prepare_sqlite_store(store_path)
    try:
        root = zarr.group(store=store)
        max_id_len = max(len(pid) for pid in ids)
        id_dtype = f"S{max(8, max_id_len)}"
        root.array(
            name="paper_id",
            data=np.asarray(ids, dtype=id_dtype),
            dtype=id_dtype,
            compressor=None,
            overwrite=True,
        )

        if zfpy_params is None:
            compressor = zarr.Blosc(
                cname=compressor_name,
                clevel=clevel,
                shuffle=zarr.Blosc.BITSHUFFLE,
            )
            target_dtype = np.float16
        else:
            compressor = ZFPY(**zfpy_params)
            target_dtype = np.float32

        dataset = root.create_dataset(
            name="embedding",
            shape=(0, vectors_store.shape[1]),
            chunks=(chunk_size, vectors_store.shape[1]),
            dtype=target_dtype,
            compressor=compressor,
            overwrite=True,
        )

        write_durations: list[float] = []
        total_start = time.perf_counter()
        for start_idx, end_idx in _chunk_indices(vectors_store.shape[0], chunk_size):
            batch = vectors_store[start_idx:end_idx]
            t0 = time.perf_counter()
            dataset.append(batch, axis=0)
            write_durations.append(time.perf_counter() - t0)
        total_duration = time.perf_counter() - total_start
        logger.info(
            "Wrote Zarr(SQLiteStore) array to {} in {:.2f}s (rows={}, chunk={})",
            store_path,
            total_duration,
            vectors_store.shape[0],
            chunk_size,
        )
    finally:
        store.close()

    return (
        AppendStats(
            total_seconds=total_duration,
            mean_seconds=statistics.fmean(write_durations),
            median_seconds=statistics.median(write_durations),
            samples=len(write_durations),
        ),
        store_path,
    )


def _measure_sqlite_size(store_path: Path) -> int:
    directory = store_path.parent
    pattern = store_path.name + "*"
    total = sum(p.stat().st_size for p in directory.glob(pattern) if p.is_file())
    logger.info("SQLite store size: {} bytes (pattern={})", total, pattern)
    return total


def _benchmark_zarr_random_reads(
    store_path: Path,
    index_batches: Sequence[Sequence[int]],
) -> RandomReadStats:
    if not index_batches:
        return RandomReadStats(0.0, 0.0, 0.0, 0, 0)
    store = SQLiteStore(str(store_path))
    try:
        dataset = zarr.open(store=store, mode="r")["embedding"]
        durations: list[float] = []
        total = 0.0
        for batch in index_batches:
            t0 = time.perf_counter()
            _ = dataset.oindex[batch, :]
            elapsed = time.perf_counter() - t0
            durations.append(elapsed)
            total += elapsed
    finally:
        store.close()

    if not durations:
        return RandomReadStats(0.0, 0.0, 0.0, 0, 0)

    return RandomReadStats(
        total_seconds=total,
        mean_seconds=statistics.fmean(durations),
        median_seconds=statistics.median(durations),
        batches=len(durations),
        batch_size=len(index_batches[0]) if index_batches else 0,
    )


def _benchmark_parquet_random_reads(
    parquet_path: Path,
    batch_id_groups: Sequence[Sequence[str]],
) -> RandomReadStats:
    if not batch_id_groups:
        return RandomReadStats(0.0, 0.0, 0.0, 0, 0)
    con = duckdb.connect(database=":memory:")
    try:
        parquet_sql = str(parquet_path).replace("'", "''")
        con.execute(
            f"CREATE TEMP VIEW embeddings AS SELECT * FROM parquet_scan('{parquet_sql}')"
        )
        durations: list[float] = []
        total = 0.0
        for ids in batch_id_groups:
            placeholders = ",".join(["?"] * len(ids))
            query = (
                f"SELECT paper_id, embedding "
                f"FROM embeddings WHERE paper_id IN ({placeholders})"
            )
            params: list[object] = list(ids)
            t0 = time.perf_counter()
            con.execute(query, params).fetchall()
            elapsed = time.perf_counter() - t0
            durations.append(elapsed)
            total += elapsed
    finally:
        con.close()

    if not durations:
        return RandomReadStats(0.0, 0.0, 0.0, 0, 0)

    return RandomReadStats(
        total_seconds=total,
        mean_seconds=statistics.fmean(durations),
        median_seconds=statistics.median(durations),
        batches=len(batch_id_groups),
        batch_size=len(batch_id_groups[0]) if batch_id_groups else 0,
    )


def _build_random_index_batches(
    total_rows: int,
    batch_size: int,
    batches: int,
    seed: int,
) -> tuple[list[list[int]], list[list[str]]]:
    if total_rows <= 0 or batch_size <= 0 or batches <= 0:
        return [], []
    rng = np.random.default_rng(seed)
    index_batches: list[list[int]] = []
    for _ in range(batches):
        batch = rng.choice(total_rows, size=min(batch_size, total_rows), replace=False)
        index_batches.append(batch.tolist())
    return index_batches, []


def _map_indices_to_ids(ids: Sequence[str], index_batches: Sequence[Sequence[int]]) -> list[list[str]]:
    mapped: list[list[str]] = []
    for batch in index_batches:
        mapped.append([ids[idx] for idx in batch])
    return mapped


def _write_npz(
    ids: Sequence[str],
    vectors: NDArray[np.float32],
    output_path: Path,
) -> float:
    vectors16 = vectors.astype(np.float16, copy=False)
    start = time.perf_counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    max_len = max((len(pid) for pid in ids), default=1)
    np.savez_compressed(
        output_path,
        paper_id=np.asarray(ids, dtype=f"<U{max_len}"),
        embedding=vectors16,
    )
    duration = time.perf_counter() - start
    logger.info("Wrote NPZ to {} in {:.2f}s (rows={})", output_path, duration, len(ids))
    return duration


def _load_npz(path: Path) -> tuple[float, np.ndarray, np.ndarray]:
    t0 = time.perf_counter()
    data = np.load(path, allow_pickle=False)
    load_time = time.perf_counter() - t0
    ids = data["paper_id"]
    embeddings = data["embedding"]
    return load_time, ids, embeddings


def _benchmark_npz_random_reads(
    embeddings: np.ndarray,
    index_batches: Sequence[Sequence[int]],
) -> RandomReadStats:
    if embeddings.size == 0 or not index_batches:
        return RandomReadStats(0.0, 0.0, 0.0, 0, 0)
    durations: list[float] = []
    total = 0.0
    for batch in index_batches:
        t0 = time.perf_counter()
        _ = embeddings[batch]
        elapsed = time.perf_counter() - t0
        durations.append(elapsed)
        total += elapsed
    return RandomReadStats(
        total_seconds=total,
        mean_seconds=statistics.fmean(durations),
        median_seconds=statistics.median(durations),
        batches=len(durations),
        batch_size=len(index_batches[0]) if index_batches else 0,
    )


def _write_zfpy(
    ids: Sequence[str],
    vectors: NDArray[np.float32],
    output_path: Path,
    *,
    mode: str,
    tolerance: float | None = None,
    rate: float | None = None,
    precision: int | None = None,
) -> tuple[float, float]:
    vectors32 = vectors.astype(np.float32, copy=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    compressed = zfpy.compress_numpy(
        vectors32,
        tolerance=tolerance or -1,
        rate=rate or -1,
        precision=precision or -1,
    )
    compress_elapsed = time.perf_counter() - start

    max_len = max((len(pid) for pid in ids), default=1)
    np.savez_compressed(
        output_path,
        paper_id=np.asarray(ids, dtype=f"<U{max_len}"),
        compressed=np.frombuffer(compressed, dtype=np.uint8),
        mode=np.array(mode),
        tolerance=np.array(tolerance if tolerance is not None else np.nan),
        rate=np.array(rate if rate is not None else np.nan),
        precision=np.array(precision if precision is not None else -1),
    )
    size = output_path.stat().st_size
    return compress_elapsed, size


def _load_zfpy(
    path: Path,
    index_batches: Sequence[Sequence[int]],
) -> tuple[float, float, np.ndarray, RandomReadStats]:
    start = time.perf_counter()
    with np.load(path, allow_pickle=False) as data:
        ids = data["paper_id"]
        compressed_bytes = data["compressed"].tobytes()
    load_elapsed = time.perf_counter() - start

    decompress_start = time.perf_counter()
    vectors = zfpy.decompress_numpy(compressed_bytes)
    decompress_elapsed = time.perf_counter() - decompress_start

    random_stats = _benchmark_npz_random_reads(vectors, index_batches)
    return load_elapsed, decompress_elapsed, ids, random_stats


def run_benchmark(args: argparse.Namespace) -> BenchmarkReport:
    source_path = Path(args.source_parquet).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ids, vectors, target_dim = _load_embeddings(source_path, args.max_rows, args.target_dim)

    parquet_path = output_dir / f"{source_path.stem}-float16.parquet"
    _write_float16_parquet(ids, vectors, parquet_path)

    npz_path = output_dir / f"{source_path.stem}-embeddings.npz"
    _write_npz(ids, vectors, npz_path)
    npz_load_seconds, npz_ids_array, npz_embeddings = _load_npz(npz_path)

    zarr_zfpy_params: dict[str, object] | None = None
    if args.zarr_use_zfpy:
        params: dict[str, object] = {}
        if args.zarr_zfpy_tolerance is not None:
            params["mode"] = zfpy.mode_fixed_accuracy
            params["tolerance"] = args.zarr_zfpy_tolerance
        elif args.zarr_zfpy_rate is not None:
            params["mode"] = zfpy.mode_fixed_rate
            params["rate"] = args.zarr_zfpy_rate
        elif args.zarr_zfpy_precision is not None:
            params["mode"] = zfpy.mode_fixed_precision
            params["precision"] = args.zarr_zfpy_precision
        else:
            params["mode"] = zfpy.mode_fixed_accuracy
            params["tolerance"] = 1e-3
        zarr_zfpy_params = params

    zarr_store_path = output_dir / f"{source_path.stem}-embeddings.sqlite"
    append_stats, _ = _write_zarr_sqlite(
        ids,
        vectors,
        chunk_size=args.chunk_size,
        compressor_name=args.compressor,
        clevel=args.compression_level,
        store_path=zarr_store_path,
        zfpy_params=zarr_zfpy_params,
    )

    index_batches, _ = _build_random_index_batches(
        total_rows=len(ids),
        batch_size=args.random_batch_size,
        batches=args.random_batches,
        seed=args.random_seed,
    )
    parquet_id_batches = _map_indices_to_ids(ids, index_batches)

    parquet_random = _benchmark_parquet_random_reads(parquet_path, parquet_id_batches)
    zarr_random = _benchmark_zarr_random_reads(zarr_store_path, index_batches)
    npz_random = _benchmark_npz_random_reads(npz_embeddings, index_batches)
    zarr_size = _measure_sqlite_size(zarr_store_path)
    npz_size = npz_path.stat().st_size

    zfpy_lossless: ZFPStats | None = None
    zfpy_lossy: ZFPStats | None = None

    if not args.skip_zfpy_lossless:
        zfpy_lossless_path = output_dir / f"{source_path.stem}-zfpy-lossless.npz"
        lossless_seconds, lossless_size = _write_zfpy(
            ids, vectors, zfpy_lossless_path, mode="lossless"
        )
        lossless_load, lossless_decompress, _, lossless_random = _load_zfpy(
            zfpy_lossless_path, index_batches
        )
        zfpy_lossless = ZFPStats(
            path=str(zfpy_lossless_path),
            size=lossless_size,
            compress_seconds=lossless_seconds,
            load_seconds=lossless_load,
            decompress_seconds=lossless_decompress,
            random_read=lossless_random,
            mode="lossless",
            parameter=None,
        )

    if not args.skip_zfpy_lossy:
        tolerance = args.zfpy_tolerance
        rate = args.zfpy_rate
        precision = args.zfpy_precision
        if tolerance is None and rate is None and precision is None:
            tolerance = 1e-3
        zfpy_lossy_path = output_dir / f"{source_path.stem}-zfpy-lossy.npz"
        lossy_seconds, lossy_size = _write_zfpy(
            ids,
            vectors,
            zfpy_lossy_path,
            mode="lossy",
            tolerance=tolerance,
            rate=rate,
            precision=precision,
        )
        lossy_load, lossy_decompress, _, lossy_random = _load_zfpy(
            zfpy_lossy_path, index_batches
        )
        lossy_param: float | int | None = tolerance if tolerance is not None else rate
        if lossy_param is None:
            lossy_param = precision
        zfpy_lossy = ZFPStats(
            path=str(zfpy_lossy_path),
            size=lossy_size,
            compress_seconds=lossy_seconds,
            load_seconds=lossy_load,
            decompress_seconds=lossy_decompress,
            random_read=lossy_random,
            mode="lossy",
            parameter=lossy_param,
        )

    report = BenchmarkReport(
        source_parquet=str(source_path),
        source_rows=len(ids),
        embedding_dim=target_dim,
        parquet_float16_path=str(parquet_path),
        parquet_float16_size=parquet_path.stat().st_size,
        parquet_float16_random_read=parquet_random,
        npz_path=str(npz_path),
        npz_size=npz_size,
        npz_load_seconds=npz_load_seconds,
        npz_random_read=npz_random,
        zarr_sqlite_path=str(zarr_store_path),
        zarr_sqlite_size=zarr_size,
        zarr_append=append_stats,
        zarr_random_read=zarr_random,
        compression_ratio_vs_parquet=parquet_path.stat().st_size / max(zarr_size, 1),
        compression_ratio_vs_npz=npz_size / max(zarr_size, 1),
        zfpy_lossless=zfpy_lossless,
        zfpy_lossy=zfpy_lossy,
    )
    return report


def _save_report(report: BenchmarkReport, output_path: Path) -> None:
    payload = asdict(report)
    # Dataclasses nested -> convert manually
    payload["parquet_float16_random_read"] = asdict(report.parquet_float16_random_read)
    payload["npz_random_read"] = asdict(report.npz_random_read)
    payload["zarr_append"] = asdict(report.zarr_append)
    payload["zarr_random_read"] = asdict(report.zarr_random_read)
    payload["zfpy_lossless"] = (
        asdict(report.zfpy_lossless) if report.zfpy_lossless is not None else None
    )
    payload["zfpy_lossy"] = (
        asdict(report.zfpy_lossy) if report.zfpy_lossy is not None else None
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Benchmark report saved to {}", output_path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-parquet", required=True, help="Path to source parquet file")
    parser.add_argument(
        "--output-dir",
        default="tmp/embedding_storage_eval",
        help="Directory to store converted artifacts",
    )
    parser.add_argument("--max-rows", type=int, default=None, help="Optional row cap for evaluation")
    parser.add_argument("--chunk-size", type=int, default=4096, help="Zarr chunk size along axis 0")
    parser.add_argument("--compressor", default="zstd", help="Blosc compressor name (e.g. zstd, lz4)")
    parser.add_argument("--compression-level", type=int, default=7, help="Blosc compression level (1-9)")
    parser.add_argument("--random-batch-size", type=int, default=512, help="Random read batch size")
    parser.add_argument("--random-batches", type=int, default=20, help="Number of random batches")
    parser.add_argument("--random-seed", type=int, default=2025, help="Random seed for reproducibility")
    parser.add_argument(
        "--target-dim",
        type=int,
        default=None,
        help="Filter embeddings to this dimension (default: dominant dimension in file)",
    )
    parser.add_argument(
        "--zarr-use-zfpy",
        action="store_true",
        help="Use zfpy compressor for Zarr store instead of Blosc",
    )
    parser.add_argument(
        "--zarr-zfpy-tolerance",
        type=float,
        default=None,
        help="Zarr zfpy tolerance parameter (selects fixed-accuracy mode)",
    )
    parser.add_argument(
        "--zarr-zfpy-rate",
        type=float,
        default=None,
        help="Zarr zfpy rate parameter (fixed-rate mode)",
    )
    parser.add_argument(
        "--zarr-zfpy-precision",
        type=int,
        default=None,
        help="Zarr zfpy precision parameter (fixed-precision mode)",
    )
    parser.add_argument(
        "--skip-zfpy-lossless",
        action="store_true",
        help="Skip zfpy lossless compression benchmark",
    )
    parser.add_argument(
        "--skip-zfpy-lossy",
        action="store_true",
        help="Skip zfpy lossy compression benchmark",
    )
    parser.add_argument(
        "--zfpy-tolerance",
        type=float,
        default=None,
        help="zfpy fixed-accuracy tolerance (default: 1e-3 if no other mode provided)",
    )
    parser.add_argument(
        "--zfpy-rate",
        type=float,
        default=None,
        help="zfpy fixed-rate parameter",
    )
    parser.add_argument(
        "--zfpy-precision",
        type=int,
        default=None,
        help="zfpy fixed-precision parameter",
    )
    parser.add_argument(
        "--report-path",
        default="tmp/embedding_storage_eval/report.json",
        help="Path to JSON report output",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    report = run_benchmark(args)
    _save_report(report, Path(args.report_path))
    readable = {
        "rows": report.source_rows,
        "dimension": report.embedding_dim,
        "parquet_size_bytes": report.parquet_float16_size,
        "zarr_sqlite_size_bytes": report.zarr_sqlite_size,
        "npz_size_bytes": report.npz_size,
        "compression_ratio": round(report.compression_ratio_vs_parquet, 3),
        "compression_ratio_vs_npz": round(report.compression_ratio_vs_npz, 3),
        "parquet_random_mean_s": round(report.parquet_float16_random_read.mean_seconds, 4),
        "npz_load_seconds": round(report.npz_load_seconds, 4),
        "npz_random_mean_s": round(report.npz_random_read.mean_seconds, 4),
        "zarr_random_mean_s": round(report.zarr_random_read.mean_seconds, 4),
        "zarr_append_mean_s": round(report.zarr_append.mean_seconds, 4),
    }
    if report.zfpy_lossless is not None:
        readable.update(
            {
                "zfpy_lossless_size_bytes": report.zfpy_lossless.size,
                "zfpy_lossless_compress_s": round(report.zfpy_lossless.compress_seconds, 4),
                "zfpy_lossless_decompress_s": round(report.zfpy_lossless.decompress_seconds, 4),
                "zfpy_lossless_random_mean_s": round(
                    report.zfpy_lossless.random_read.mean_seconds, 4
                ),
            }
        )
    if report.zfpy_lossy is not None:
        readable.update(
            {
                "zfpy_lossy_size_bytes": report.zfpy_lossy.size,
                "zfpy_lossy_compress_s": round(report.zfpy_lossy.compress_seconds, 4),
                "zfpy_lossy_decompress_s": round(report.zfpy_lossy.decompress_seconds, 4),
                "zfpy_lossy_random_mean_s": round(
                    report.zfpy_lossy.random_read.mean_seconds, 4
                ),
                "zfpy_lossy_param": report.zfpy_lossy.parameter,
            }
        )
    print(json.dumps(readable, indent=2))


if __name__ == "__main__":
    main()
