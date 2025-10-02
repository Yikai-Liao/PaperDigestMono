"""Utilities to migrate legacy PaperDigest data into the new local-first layout."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, cast

import polars as pl
import typer
from huggingface_hub import HfApi, hf_hub_download
from loguru import logger

__all__ = ["MigrationConfig", "LegacyMigrator", "app"]

ISO_MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})")

SUMMARY_FIELD_ORDER: tuple[str, ...] = (
    "id",
    "title",
    "slug",
    "one_sentence_summary",
    "problem_background",
    "method",
    "experiment",
    "further_thoughts",
    "reasoning_step",
    "summary",
    "abstract",
    "authors",
    "institution",
    "categories",
    "keywords",
    "preference",
    "score",
    "created",
    "updated",
    "summary_time",
    "migrated_at",
    "source",
    "source_file",
    "lang",
    "model",
    "temperature",
    "top_p",
    "year",
    "date",
    "license",
    "show",
)


@dataclass(slots=True)
class MigrationConfig:
    """Runtime configuration for the legacy data migrator."""

    output_root: Path
    reference_roots: tuple[Path, Path]
    hf_dataset: str | None
    years: tuple[int, ...] | None
    models: tuple[str, ...] | None
    dry_run: bool
    force: bool
    cache_dir: Path | None = None


class LegacyMigrator:
    """Orchestrates the migration from legacy repositories to local data folders."""

    def __init__(self, config: MigrationConfig):
        self.config = config
        self.output_root = config.output_root.resolve()
        self.paper_digest_root = config.reference_roots[0].resolve()
        self.paper_digest_action_root = config.reference_roots[1].resolve()
        self.api = HfApi() if config.hf_dataset else None
        self.metadata_frames: list[pl.DataFrame] = []
        self.embedding_backlogs: dict[str, list[pl.DataFrame]] = defaultdict(list)
        self.report: dict[str, object] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"years": {}, "total_rows": 0},
            "embeddings": {},
            "preferences": {
                "input_files": 0,
                "rows": 0,
                "unique_ids": 0,
                "output_files": 0,
                "skipped_rows": 0,
            },
            "summaries": {
                "input_files": 0,
                "records": 0,
                "output_files": 0,
                "skipped": 0,
            },
            "warnings": [],
        }
        self._relative_roots: tuple[Path, ...] = (
            self.paper_digest_root,
            self.paper_digest_action_root,
            self.paper_digest_root.parent,
        )

    def run(self) -> dict[str, object]:
        if self.api is not None:
            self._process_metadata_and_embeddings()
        else:
            logger.warning("HF dataset not provided; skipping metadata/embedding migration")

        self._process_preferences()
        self._process_summaries()

        if not self.config.dry_run:
            self._write_report()
        return self.report

    def _process_metadata_and_embeddings(self) -> None:
        dataset = self.config.hf_dataset
        assert dataset is not None  # guarded by caller

        years = self._determine_years(dataset)
        logger.info("Preparing to migrate {} years of metadata/embeddings", len(years))

        for year in sorted(years):
            try:
                frame = self._load_year_frame(dataset, year)
            except Exception as exc:  # pragma: no cover - defensive guard
                warning = f"Failed to load dataset year {year}: {exc!r}"
                logger.error(warning)
                self._append_warning(warning)
                continue

            artifacts = self._prepare_year_artifacts(year, frame)
            self.metadata_frames.append(artifacts[0])
            self._write_year_artifacts(year, artifacts)

        self._finalize_metadata()
        self._finalize_embeddings()

    def _determine_years(self, dataset: str) -> list[int]:
        if self.config.years:
            return list(dict.fromkeys(self.config.years))

        assert self.api is not None
        files = self.api.list_repo_files(dataset, repo_type="dataset")
        years: list[int] = []
        for name in files:
            if not name.endswith(".parquet"):
                continue
            stem = Path(name).stem
            if stem.isdigit():
                years.append(int(stem))
        if not years:
            raise RuntimeError(f"No parquet files found in dataset {dataset}")
        return years

    def _load_year_frame(self, dataset: str, year: int) -> pl.DataFrame:
        logger.info("Loading dataset {} for year {}", dataset, year)
        filename = f"{year}.parquet"
        path = hf_hub_download(
            repo_id=dataset,
            filename=filename,
            repo_type="dataset",
            local_dir=self.config.cache_dir,
        )
        logger.debug("Resolved parquet path {}", path)
        return pl.read_parquet(path)

    def _prepare_year_artifacts(
        self,
        year: int,
        frame: pl.DataFrame,
    ) -> tuple[pl.DataFrame, dict[str, pl.DataFrame], dict[str, pl.DataFrame]]:
        metadata_df = self._build_metadata_frame(frame)
        embeddings = self._build_embedding_frames(frame)
        backlogs = self._build_backlog_frames(frame, embeddings)

        metadata_report = cast(dict[str, Any], self.report["metadata"])
        years_report = cast(dict[str, int], metadata_report["years"])  # type: ignore[index]
        years_report[str(year)] = metadata_df.height
        total_rows = int(metadata_report.get("total_rows") or 0) + metadata_df.height
        metadata_report["total_rows"] = total_rows

        embeddings_report = cast(dict[str, Any], self.report["embeddings"])  # type: ignore[assignment]
        for model, data in embeddings.items():
            model_report = embeddings_report.setdefault(
                model,
                {
                    "years": {},
                    "total_rows": 0,
                    "dimension": self._frame_vector_dimension(data),
                },
            )
            model_report = cast(dict[str, Any], model_report)
            years_info = cast(dict[str, int], model_report["years"])  # type: ignore[index]
            years_info[str(year)] = data.height
            model_report["total_rows"] = int(model_report.get("total_rows") or 0) + data.height

        return metadata_df, embeddings, backlogs

    def _build_metadata_frame(self, frame: pl.DataFrame) -> pl.DataFrame:
        columns = frame.columns
        required = {"id", "title", "abstract", "categories", "authors", "created", "updated"}
        missing = required - set(columns)
        if missing:
            warning = f"Metadata frame missing columns: {', '.join(sorted(missing))}"
            logger.warning(warning)
            self._append_warning(warning)

        def _join_list(column: str, separator: str) -> pl.Expr:
            if column in columns:
                return pl.col(column).list.join(separator).fill_null("")
            return pl.lit("")

        def _col(name: str) -> pl.Expr:
            if name in columns:
                return pl.col(name).alias(name)
            return pl.lit("").alias(name)

        metadata_df = (
            frame.select(
                pl.col("id").alias("paper_id"),
                _col("title"),
                _col("abstract"),
                pl.when(pl.col("categories").is_not_null())
                .then(pl.col("categories").list.join(";"))
                .otherwise(pl.lit(""))
                .alias("categories"),
                pl.when(pl.col("categories").is_not_null())
                .then(pl.col("categories").list.first())
                .otherwise(pl.lit(""))
                .alias("primary_category"),
                _join_list("authors", ";").alias("authors"),
                _col("created").alias("published_at"),
                _col("updated").alias("updated_at"),
                _col("doi"),
                _col("comment"),
                _col("journal_ref"),
                _col("license"),
            )
            .with_columns(
                pl.lit("legacy_migration").alias("source"),
            )
            .sort("paper_id")
        )
        return metadata_df

    def _build_embedding_frames(self, frame: pl.DataFrame) -> dict[str, pl.DataFrame]:
        available_models = self._detect_embedding_columns(frame)
        target_models = (
            list(dict.fromkeys(self.config.models))
            if self.config.models
            else available_models
        )

        missing = [model for model in target_models if model not in available_models]
        for model in missing:
            warning = f"Embedding column '{model}' not available; skipping"
            logger.warning(warning)
            self._append_warning(warning)

        embeddings: dict[str, pl.DataFrame] = {}
        for model in target_models:
            if model not in available_models:
                continue
            dtype = frame.schema[model]
            if isinstance(dtype, pl.Array):
                cast_expr = pl.col(model).arr.to_list().cast(pl.List(pl.Float32))
            elif isinstance(dtype, pl.List):
                cast_expr = pl.col(model).cast(pl.List(pl.Float32))
            else:  # pragma: no cover - defensive guard
                warning = f"Column '{model}' is not recognised as embedding type ({dtype})"
                logger.warning(warning)
                self._append_warning(warning)
                continue

            embedding_df = (
                frame.select(
                    pl.col("id").alias("paper_id"),
                    cast_expr.alias("embedding"),
                    pl.col("updated").alias("generated_at"),
                )
                .with_columns(
                    pl.col("embedding").list.len().alias("model_dim"),
                    pl.lit(f"hf:{self.config.hf_dataset or 'unknown'}").alias("source"),
                )
                .sort("paper_id")
            )
            embeddings[model] = embedding_df
        return embeddings

    def _build_backlog_frames(
        self,
        frame: pl.DataFrame,
        embeddings: dict[str, pl.DataFrame],
    ) -> dict[str, pl.DataFrame]:
        backlogs: dict[str, pl.DataFrame] = {}
        for model in embeddings:
            missing = frame.filter(pl.col(model).is_null()).select(
                pl.col("id").alias("paper_id"),
                pl.lit("null_embedding").alias("missing_reason"),
                pl.lit("legacy_migration").alias("origin"),
                pl.lit(self.report["generated_at"]).alias("queued_at"),
            )
            if not missing.is_empty():
                backlogs[model] = missing
        return backlogs

    def _write_year_artifacts(
        self,
        year: int,
        artifacts: tuple[pl.DataFrame, dict[str, pl.DataFrame], dict[str, pl.DataFrame]],
    ) -> None:
        metadata_df, embeddings, backlogs = artifacts

        metadata_dir = self.output_root / "metadata"
        metadata_path = metadata_dir / f"metadata-{year}.csv"
        self._write_csv(metadata_path, metadata_df, overwrite=True)

        embeddings_dir = self.output_root / "embeddings"
        for model, df in embeddings.items():
            model_dir = embeddings_dir / model
            parquet_path = model_dir / f"{year}.parquet"
            self._write_parquet(parquet_path, df, overwrite=True)

            backlog = backlogs.get(model)
            if backlog is not None and not backlog.is_empty():
                self.embedding_backlogs[model].append(backlog)

    def _finalize_metadata(self) -> None:
        if not self.metadata_frames:
            return
        combined = pl.concat(self.metadata_frames, how="vertical")
        combined = combined.unique(subset=["paper_id"], keep="last")
        sort_columns = [col for col in ("published_at", "paper_id") if col in combined.columns]
        if sort_columns:
            combined = combined.sort(sort_columns)
        latest_path = (self.output_root / "metadata") / "latest.csv"
        self._write_csv(latest_path, combined, overwrite=True)

    def _finalize_embeddings(self) -> None:
        embeddings_report = cast(dict[str, Any], self.report["embeddings"])  # type: ignore[assignment]
        embeddings_dir = self.output_root / "embeddings"

        for model, raw_report in embeddings_report.items():
            model_report = cast(dict[str, Any], raw_report)
            years_info = cast(dict[str, int], model_report.get("years", {}))
            backlog_frames = self.embedding_backlogs.get(model, [])
            model_dir = embeddings_dir / model

            if backlog_frames:
                backlog_df = pl.concat(backlog_frames, how="vertical").unique(subset=["paper_id"], keep="last")
                backlog_path = model_dir / "backlog.parquet"
                self._write_parquet(backlog_path, backlog_df, overwrite=True)

            manifest_payload = {
                "model": model,
                "dimension": int(model_report.get("dimension") or 0),
                "total_rows": int(model_report.get("total_rows") or 0),
                "years": {year: int(count) for year, count in years_info.items()},
                "files": sorted(f"{year}.parquet" for year in years_info.keys()),
                "generated_at": str(self.report["generated_at"]),
                "source": "legacy_migration",
            }
            manifest_path = model_dir / "manifest.json"
            self._write_json(manifest_path, manifest_payload, overwrite=True)

    # ------------------------------------------------------------------
    # Preference migration
    def _process_preferences(self) -> None:
        preference_dirs = [
            self.paper_digest_root / "preference",
            self.paper_digest_action_root / "preference",
        ]
        preference_files = [
            path
            for directory in preference_dirs
            if directory.exists()
            for path in sorted(directory.glob("*.csv"))
        ]
        if not preference_files:
            logger.warning("No preference CSV files found; skipping")
            return

        logger.info("Merging {} preference files", len(preference_files))
        entries: list[dict[str, str]] = []
        latest: dict[str, dict[str, str]] = {}
        skipped_rows = 0
        generated_at = str(self.report.get("generated_at", ""))

        for csv_path in preference_files:
            try:
                df = pl.read_csv(
                    csv_path,
                    columns=["id", "preference"],
                    schema={"id": pl.String, "preference": pl.String},
                    ignore_errors=True,
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                warning = f"Failed to read preference file {csv_path}: {exc!r}"
                logger.warning(warning)
                self._append_warning(warning)
                continue

            if df.is_empty():
                continue

            month = csv_path.stem
            recorded_at = self._recorded_at_from_month(month, generated_at)
            for record in df.iter_rows(named=True):
                paper_id = (record.get("id") or "").strip()
                preference = (record.get("preference") or "").strip()
                if not paper_id or not preference:
                    skipped_rows += 1
                    continue
                event = {
                    "paper_id": paper_id,
                    "preference": preference,
                    "recorded_at": recorded_at,
                    "source_month": month,
                }
                entries.append(event)
                latest[event["paper_id"]] = event

        if not entries:
            logger.warning("Preference inputs were empty")
            return

        entries.sort(key=lambda item: self._month_order(item["source_month"]))

        self.report["preferences"]["input_files"] = len(preference_files)  # type: ignore[index]
        self.report["preferences"]["rows"] = len(entries)  # type: ignore[index]
        self.report["preferences"]["skipped_rows"] = skipped_rows  # type: ignore[index]
        self.report["preferences"]["unique_ids"] = len(latest)  # type: ignore[index]

        grouped_by_year: dict[str, list[dict[str, str]]] = defaultdict(list)
        for event in entries:
            month_label = event["source_month"]
            match = ISO_MONTH_RE.match(month_label)
            year_key = match.group("year") if match else "unknown"
            grouped_by_year[year_key].append(
                {
                    "paper_id": event["paper_id"],
                    "preference": event["preference"],
                    "recorded_at": event["recorded_at"] or generated_at,
                }
            )

        preferences_dir = self.output_root / "preferences"
        output_files = 0
        for year_key, rows in grouped_by_year.items():
            df = pl.DataFrame(
                rows,
                schema={
                    "paper_id": pl.String,
                    "preference": pl.String,
                    "recorded_at": pl.String,
                },
            ).sort(["paper_id", "recorded_at"])
            target = preferences_dir / f"events-{year_key}.csv"
            self._write_csv(target, df, overwrite=True)
            output_files += 1

        self.report["preferences"]["output_files"] = output_files  # type: ignore[index]

    # ------------------------------------------------------------------
    # Summary migration
    def _process_summaries(self) -> None:
        summary_sources = [
            (self.paper_digest_root / "raw", "papersys.raw"),
            (self.paper_digest_action_root / "summarized", "papersys.action"),
        ]

        records: dict[str, dict] = {}
        input_files = 0

        for directory, source_label in summary_sources:
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.json")):
                input_files += 1
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    warning = f"Failed to read summary JSON {path}: {exc!r}"
                    logger.warning(warning)
                    self._append_warning(warning)
                    continue
                normalized = self._normalize_summary(record, path.stem, source_label, path)
                if normalized is None:
                    continue
                records[normalized["id"]] = normalized

            for path in sorted(directory.rglob("*.jsonl")):
                input_files += 1
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        warning = f"Invalid JSONL entry in {path}#{line_number}: {exc.msg}"
                        logger.warning(warning)
                        self._append_warning(warning)
                        continue
                    normalized = self._normalize_summary(record, record.get("id") or f"{path.stem}-{line_number}", source_label, path)
                    if normalized is None:
                        continue
                    records[normalized["id"]] = normalized

        if not records:
            logger.warning("No summary records found; skipping")
            return

        self.report["summaries"]["input_files"] = input_files  # type: ignore[index]
        self.report["summaries"]["records"] = len(records)  # type: ignore[index]

        grouped: dict[str, list[dict]] = {}
        for data in records.values():
            month = data.pop("__month__")
            grouped.setdefault(month, []).append(data)

        for month, rows in grouped.items():
            rows.sort(key=lambda item: item["id"])
            target = self.output_root / "summaries" / f"{month}.jsonl"
            self._write_jsonl(target, rows, overwrite=True)

        self.report["summaries"]["output_files"] = len(grouped)  # type: ignore[index]

    # ------------------------------------------------------------------
    # Helpers
    def _write_csv(self, path: Path, frame: pl.DataFrame, *, overwrite: bool = False) -> None:
        if self.config.dry_run:
            logger.info("[dry-run] Would write CSV {} ({} rows)", path, frame.height)
            return
        if path.exists() and not (overwrite or self.config.force):
            logger.warning("Skipping existing file {} (use --force to overwrite)", path)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_csv(path)
        logger.info("Wrote CSV {} ({} rows)", path, frame.height)

    def _write_parquet(self, path: Path, frame: pl.DataFrame, *, overwrite: bool = False) -> None:
        if self.config.dry_run:
            logger.info("[dry-run] Would write Parquet {} ({} rows)", path, frame.height)
            return
        if path.exists() and not (overwrite or self.config.force):
            logger.warning("Skipping existing file {} (use --force to overwrite)", path)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)
        logger.info("Wrote Parquet {} ({} rows)", path, frame.height)

    def _write_jsonl(self, path: Path, rows: Sequence[dict], *, overwrite: bool = False) -> None:
        if self.config.dry_run:
            logger.info("[dry-run] Would write JSONL {} ({} rows)", path, len(rows))
            return
        if path.exists() and not (overwrite or self.config.force):
            logger.warning("Skipping existing file {} (use --force to overwrite)", path)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                ordered = self._ordered_payload(row)
                fh.write(json.dumps(ordered, ensure_ascii=False) + "\n")
        logger.info("Wrote JSONL {} ({} rows)", path, len(rows))

    def _write_json(self, path: Path, payload: dict, *, overwrite: bool = False) -> None:
        if self.config.dry_run:
            logger.info("[dry-run] Would write JSON {}", path)
            return
        if path.exists() and not (overwrite or self.config.force):
            logger.warning("Skipping JSON write {}; file exists (use --force to overwrite)", path)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("Wrote JSON {}", path)

    def _write_report(self) -> None:
        report_path = self.output_root / "migration-report.json"
        self._write_json(report_path, cast(dict, self.report), overwrite=True)

    @staticmethod
    def _frame_vector_dimension(frame: pl.DataFrame) -> int:
        if frame.is_empty():
            return 0
        try:
            result = frame.select(pl.col("embedding").list.len().max()).item()
        except Exception:  # pragma: no cover - dimensional inference fallback
            return 0
        if result is None:
            return 0
        return int(result)

    def _safe_relative(self, path: Path) -> str:
        for root in self._relative_roots:
            try:
                return str(path.relative_to(root))
            except ValueError:
                continue
        return str(path)

    @staticmethod
    def _detect_embedding_columns(frame: pl.DataFrame) -> list[str]:
        columns: list[str] = []
        for name, dtype in frame.schema.items():
            if isinstance(dtype, pl.Array):
                inner = getattr(dtype, "inner", None)
                is_numeric = getattr(inner, "is_numeric", None)
                if callable(is_numeric) and is_numeric():
                    columns.append(name)
            elif isinstance(dtype, pl.List):
                inner = getattr(dtype, "inner", None)
                is_numeric = getattr(inner, "is_numeric", None)
                if callable(is_numeric) and is_numeric():
                    columns.append(name)
        return columns

    @staticmethod
    def _month_order(label: str) -> tuple[int, int]:
        match = ISO_MONTH_RE.match(label)
        if match:
            return int(match.group("year")), int(match.group("month"))
        if label == "init":
            return (-1, -1)
        return (9999, 12)

    @staticmethod
    def _recorded_at_from_month(month_label: str, fallback: str) -> str:
        match = ISO_MONTH_RE.match(month_label)
        if not match:
            return fallback
        try:
            timestamp = datetime(
                int(match.group("year")),
                int(match.group("month")),
                1,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return fallback
        return timestamp.isoformat()

    def _ordered_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys_in_priority = [key for key in SUMMARY_FIELD_ORDER if key in payload]
        seen = set(keys_in_priority)
        remaining = sorted(key for key in payload.keys() if key not in seen)
        ordered: dict[str, Any] = {}
        for key in keys_in_priority + remaining:
            ordered[key] = payload[key]
        return ordered

    def _normalize_summary(
        self,
        record: dict,
        fallback_id: str,
        source: str,
        source_file: Path,
    ) -> dict | None:
        paper_id = record.get("id") or fallback_id
        if not paper_id:
            warning = f"Summary record in {self._safe_relative(source_file)} missing id; skipping"
            logger.warning(warning)
            self._append_warning(warning)
            return None

        summary_time = self._extract_datetime(
            record.get("summary_time")
            or record.get("updated")
            or record.get("created"),
        )
        if summary_time is None:
            month = "unknown"
        else:
            month = f"{summary_time.year:04d}-{summary_time.month:02d}"

        normalized = dict(record)
        normalized["id"] = paper_id
        normalized["source"] = source
        normalized["source_file"] = self._safe_relative(source_file)
        normalized["migrated_at"] = str(self.report.get("generated_at", ""))
        normalized.setdefault("summary_time", summary_time.isoformat() if summary_time else "")
        normalized["__month__"] = month
        return normalized

    @staticmethod
    def _extract_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        cleaned = value.strip()
        try:
            if cleaned.endswith("Z"):
                cleaned = cleaned[:-1] + "+00:00"
            return datetime.fromisoformat(cleaned)
        except ValueError:
            pass
        match = ISO_MONTH_RE.match(cleaned)
        if match:
            try:
                return datetime(int(match.group("year")), int(match.group("month")), 1, tzinfo=timezone.utc)
            except ValueError:  # pragma: no cover - invalid calendar dates
                return None
        return None

    def _append_warning(self, message: str) -> None:
        warnings = self.report.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(message)


# ----------------------------------------------------------------------
# Typer CLI shim
app = typer.Typer(help="Legacy data migration helpers")


@app.command("run")
def migrate_command(
    year: list[int] = typer.Option(None, "--year", help="Year to migrate (repeatable)"),
    model: list[str] = typer.Option(None, "--model", help="Embedding model alias to export"),
    output_root: Path = typer.Option(Path("."), "--output-root", help="Destination root for migrated data"),
    reference_root: Path = typer.Option(Path("reference"), "--reference-root", help="Root directory of legacy repositories"),
    hf_dataset: str = typer.Option("lyk/ArxivEmbedding", "--hf-dataset", help="Hugging Face dataset id for metadata embeddings"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without writing files"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    cache_dir: Path | None = typer.Option(None, "--cache-dir", help="Optional cache directory for HF downloads"),
) -> None:
    reference_root = reference_root.resolve()
    paper_digest_root = reference_root / "PaperDigest"
    paper_digest_action_root = reference_root / "PaperDigestAction"

    config = MigrationConfig(
        output_root=output_root.resolve(),
        reference_roots=(paper_digest_root, paper_digest_action_root),
        hf_dataset=hf_dataset or None,
        years=tuple(year) if year else None,
        models=tuple(model) if model else None,
        dry_run=dry_run,
        force=force,
        cache_dir=cache_dir.resolve() if cache_dir else None,
    )

    migrator = LegacyMigrator(config)
    report = migrator.run()
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    app()
