"""Filter embedding parquet files to match the configured vector dimension.

The script scans a model's parquet directory, drops rows whose embedding length
differs from the expected dimension, and writes cleaned parquet files to a
destination directory (defaults to tmp/). Production data is never modified in-place.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import polars as pl
from loguru import logger


@dataclass(slots=True)
class FileStat:
    path: Path
    kept_rows: int
    dropped_rows: int


def _collect_lengths(parquet_path: Path) -> pl.DataFrame:
    """Return counts grouped by embedding length."""
    return (
        pl.scan_parquet(str(parquet_path))
        .select(pl.col("embedding").list.len().alias("dim"))
        .group_by("dim")
        .len()
        .rename({"len": "rows"})
        .collect()
    )


def _to_dim_map(length_counts: pl.DataFrame) -> dict[int, int]:
    return {
        int(dim): int(rows)
        for dim, rows in zip(length_counts["dim"].to_list(), length_counts["rows"].to_list())
    }


def _filter_parquet(parquet_path: Path, expected_dim: int, output_path: Path) -> FileStat:
    """Filter rows by embedding dimension and persist to output parquet."""
    logger.info("Processing {}", parquet_path)
    length_counts = _collect_lengths(parquet_path)
    dims = _to_dim_map(length_counts)
    kept_rows = dims.get(expected_dim, 0)
    dropped_rows = sum(rows for dim, rows in dims.items() if dim != expected_dim)
    if kept_rows == 0:
        logger.warning(
            "Skipping {} because no rows matched expected dimension {}", parquet_path, expected_dim
        )
        return FileStat(output_path, kept_rows=0, dropped_rows=dropped_rows)

    lazy_frame = pl.scan_parquet(str(parquet_path)).filter(
        pl.col("embedding").list.len() == expected_dim
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lazy_frame.sink_parquet(
        str(output_path),
        compression="zstd",
        compression_level=5,
    )

    logger.info(
        "Wrote cleaned parquet to {} (kept={}, dropped={})",
        output_path,
        kept_rows,
        dropped_rows,
    )
    return FileStat(output_path, kept_rows=kept_rows, dropped_rows=dropped_rows)


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    if not manifest_path.exists():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _update_manifest(
    manifest: dict[str, object],
    stats: Iterable[FileStat],
    expected_dim: int,
    destination: Path,
) -> dict[str, object]:
    years: dict[str, int] = {}
    total_rows = 0
    for stat in stats:
        if stat.kept_rows == 0:
            continue
        year = stat.path.stem
        years[year] = stat.kept_rows
        total_rows += stat.kept_rows

    manifest["dimension"] = expected_dim
    manifest["total_rows"] = total_rows
    manifest["years"] = dict(sorted(years.items()))
    manifest["files"] = [f"{year}.parquet" for year in sorted(years.keys())]
    manifest["cleaned_destination"] = str(destination)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Path to the embedding model directory containing year parquet files",
    )
    parser.add_argument(
        "--expected-dim",
        type=int,
        required=True,
        help="Expected embedding vector dimension",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to store cleaned parquet files (default: tmp/embedding_clean/<alias>)",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Generate an updated manifest.json alongside cleaned parquet files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report mismatched dimensions without writing files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_dir = Path(args.model_dir).resolve()
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    alias = model_dir.name
    destination = Path(args.output_dir) if args.output_dir else Path("tmp/embedding_clean") / alias
    manifest_path = model_dir / "manifest.json"
    manifest_data = _load_manifest(manifest_path)

    parquet_files = sorted(model_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {model_dir}")

    collected_stats: list[FileStat] = []
    for parquet_path in parquet_files:
        counts = _collect_lengths(parquet_path)
        dims = _to_dim_map(counts)
        logger.info("Dimension counts for {}: {}", parquet_path, dims)
        if len(dims) == 1 and args.expected_dim in dims:
            if args.dry_run:
                continue
            output_path = destination / parquet_path.name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pl.read_parquet(parquet_path).write_parquet(
                output_path, compression="zstd", compression_level=5
            )
            logger.info("Copied {} without changes", parquet_path.name)
            collected_stats.append(
                FileStat(
                    path=output_path,
                    kept_rows=dims[args.expected_dim],
                    dropped_rows=0,
                )
            )
            continue

        if args.dry_run:
            continue

        output_path = destination / parquet_path.name
        stat = _filter_parquet(parquet_path, args.expected_dim, output_path)
        collected_stats.append(stat)

    if args.dry_run:
        logger.info("Dry-run complete; no files were written.")
        return

    if args.update_manifest:
        updated_manifest = _update_manifest(manifest_data, collected_stats, args.expected_dim, destination)
        manifest_out = destination / "manifest.json"
        manifest_out.write_text(json.dumps(updated_manifest, indent=2), encoding="utf-8")
        logger.info("Updated manifest written to {}", manifest_out)


if __name__ == "__main__":
    main()
