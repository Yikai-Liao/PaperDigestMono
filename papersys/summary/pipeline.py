"""High-level orchestration for the summary pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from loguru import logger
import polars as pl

from papersys.config import AppConfig, SummaryPipelineConfig
from papersys.config.llm import LLMConfig

from .generator import SummaryGenerator
from .models import SummaryArtifact, SummarySource
from .renderer import SummaryRenderer
from .fetcher import (
    ArxivContentFetcher,
    ContentUnavailableError,
    FetchResult,
    StubContentFetcher,
    SummaryContentFetcher,
)


_SUMMARY_SOURCE_TAG = "papersys.summary.pipeline"


@dataclass(slots=True)
class SummaryDataSources:
    """Resolved filesystem locations used by the summary pipeline."""

    pdf_dir: Path
    markdown_dir: Path

    def ensure_directories(self) -> None:
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)

    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.pdf_dir.exists():
            missing.append("pdf_dir")
        if not self.markdown_dir.exists():
            missing.append("markdown_dir")
        return tuple(missing)


@dataclass(slots=True)
class SummaryRunReport:
    """Report containing artefacts and filesystem outputs for a summary run."""

    artifacts: list[SummaryArtifact]
    jsonl_path: Path
    manifest_path: Path
    markdown_dir: Path


class SummaryPipeline:
    """Convenience wrapper that wires together PDF fetching, LLM summarisation and rendering."""

    def __init__(
        self,
        config: AppConfig,
        *,
        base_path: Path | None = None,
        template: str | None = None,
        fetcher: SummaryContentFetcher | None = None,
    ) -> None:
        if config.summary_pipeline is None:
            raise ValueError("summary_pipeline config is required for summary operations")
        self._config = config
        self._pipeline_cfg: SummaryPipelineConfig = config.summary_pipeline
        self._base_path = self._resolve_base_path(base_path)
        self._summaries_root = (self._base_path / "summaries").resolve()
        self._summaries_root.mkdir(parents=True, exist_ok=True)
        self._sources = self._resolve_sources()
        self._renderer = SummaryRenderer(template=template)

        llm_settings = self._pipeline_cfg.llm
        self._llm_config = self._resolve_llm_config(llm_settings.model)
        self._generator = SummaryGenerator(
            self._llm_config,
            default_language=llm_settings.language,
            allow_latex=llm_settings.enable_latex,
        )
        self._fetcher = fetcher or self._create_fetcher()

    def _resolve_sources(self) -> SummaryDataSources:
        pdf_dir = self._resolve_path(self._pipeline_cfg.pdf.output_dir)
        markdown_dir = pdf_dir / "markdown"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        return SummaryDataSources(pdf_dir=pdf_dir, markdown_dir=markdown_dir)

    def _resolve_base_path(self, base_path: Path | None) -> Path:
        if base_path is not None:
            return Path(base_path).resolve()
        if self._config.data_root is not None:
            return Path(self._config.data_root).resolve()
        return Path.cwd()

    def _resolve_path(self, fragment: str | Path) -> Path:
        path = Path(fragment)
        if not path.is_absolute():
            path = (Path(self._base_path) / path).resolve()
        return path

    def _resolve_llm_config(self, alias: str) -> LLMConfig:
        for llm in self._config.llms:
            if llm.alias == alias:
                return llm
        raise ValueError(f"LLM alias '{alias}' not found in configuration")

    def _create_fetcher(self) -> SummaryContentFetcher:
        pdf_cfg = self._pipeline_cfg.pdf
        if _is_stub_llm(self._llm_config):
            return StubContentFetcher(self._sources.pdf_dir)
        return ArxivContentFetcher(
            pdf_dir=self._sources.pdf_dir,
            delay=pdf_cfg.delay,
            max_retry=pdf_cfg.max_retry,
            fetch_latex_source=pdf_cfg.fetch_latex_source,
        )

    # ------------------------------------------------------------------
    def describe_sources(self) -> SummaryDataSources:
        """Return the resolved data sources without mutating state."""
        return SummaryDataSources(
            pdf_dir=self._sources.pdf_dir,
            markdown_dir=self._sources.markdown_dir,
        )

    def run(
        self,
        sources: Iterable[SummarySource],
        *,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> list[SummaryArtifact]:
        self._sources.ensure_directories()
        if dry_run:
            logger.info(
                "Summary pipeline dry-run completed. PDF dir={}, markdown dir={}",
                self._sources.pdf_dir,
                self._sources.markdown_dir,
            )
            return []

        markdown_base = self._sources.markdown_dir
        if run_id:
            markdown_base = (markdown_base / run_id).resolve()
            markdown_base.mkdir(parents=True, exist_ok=True)
        else:
            markdown_base.mkdir(parents=True, exist_ok=True)

        artifacts: list[SummaryArtifact] = []
        for source in sources:
            try:
                fetch_result: FetchResult = self._fetcher.fetch(source)
            except ContentUnavailableError as exc:
                logger.warning("Skipped summary for {}: {}", source.paper_id, exc)
                continue
            document = self._generator.generate(source, context=fetch_result.markdown_context)
            markdown = self._renderer.render(document)
            markdown_path = markdown_base / f"{source.paper_id}.md"
            markdown_path.write_text(markdown, encoding="utf-8")
            artifacts.append(
                SummaryArtifact(
                    source=source,
                    pdf_path=fetch_result.pdf_path,
                    markdown_path=markdown_path,
                    document=document,
                    markdown=markdown,
                )
            )
            logger.info(
                "Summary generated for {} | pdf={} | markdown={}",
                source.paper_id,
                fetch_result.pdf_path.name,
                markdown_path.name,
            )
        return artifacts

    def run_and_save(
        self,
        sources: Iterable[SummarySource],
        *,
        run_at: datetime | None = None,
        limit: int | None = None,
    ) -> SummaryRunReport:
        source_list = list(sources)
        if limit is not None:
            source_list = source_list[:limit]

        run_at = run_at or datetime.now(timezone.utc)
        run_id = run_at.strftime("%Y%m%d-%H%M%S")

        artifacts = self.run(source_list, run_id=run_id)

        jsonl_path = (self._summaries_root / f"{run_at:%Y-%m}.jsonl").resolve()
        manifest_path = (self._summaries_root / f"manifest-{run_id}.json").resolve()
        markdown_dir = (self._sources.markdown_dir / run_id).resolve()

        if artifacts:
            self._append_jsonl(artifacts, jsonl_path, run_at)

        manifest = self._build_manifest(
            run_id=run_id,
            run_at=run_at,
            total_sources=len(source_list),
            artifacts=artifacts,
            jsonl_path=jsonl_path,
            markdown_dir=markdown_dir,
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(
            "Summary run {} complete: {} summaries written",
            run_id,
            len(artifacts),
        )

        return SummaryRunReport(
            artifacts=artifacts,
            jsonl_path=jsonl_path,
            manifest_path=manifest_path,
            markdown_dir=markdown_dir,
        )

    def load_sources_from_recommendations(
        self,
        recommendation_path: Path,
        *,
        limit: int | None = None,
    ) -> list[SummarySource]:
        path = recommendation_path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Recommendation file not found: {path}")

        suffix = path.suffix.lower()
        if suffix in {".parquet"}:
            frame = pl.read_parquet(path)
        elif suffix in {".json", ".jsonl", ".ndjson"}:
            frame = pl.read_ndjson(path)
        else:
            raise ValueError(f"Unsupported recommendation file format: {path.suffix}")

        if limit is not None:
            frame = frame.head(limit)

        sources: list[SummarySource] = []
        language = self._pipeline_cfg.llm.language

        for row in frame.iter_rows(named=True):
            paper_id = row.get("id") or row.get("paper_id")
            if not paper_id:
                continue
            title = row.get("title") or ""
            abstract = row.get("abstract") or ""
            score = row.get("score")
            categories = row.get("categories")
            if isinstance(categories, str):
                categories = [item.strip() for item in categories.split(";") if item.strip()]
            sources.append(
                SummarySource(
                    paper_id=str(paper_id),
                    title=str(title),
                    abstract=str(abstract),
                    pdf_url=None,
                    language=language,
                    score=float(score) if isinstance(score, (int, float)) else None,
                    categories=categories if isinstance(categories, list) else None,
                )
            )

        return sources

    # ------------------------------------------------------------------
    def _append_jsonl(
        self,
        artifacts: Sequence[SummaryArtifact],
        jsonl_path: Path,
        run_at: datetime,
    ) -> None:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as fp:
            for artifact in artifacts:
                record = self._artifact_to_record(artifact, run_at)
                fp.write(json.dumps(record, ensure_ascii=False))
                fp.write("\n")

    def _artifact_to_record(self, artifact: SummaryArtifact, run_at: datetime) -> dict[str, object]:
        try:
            markdown_rel = artifact.markdown_path.relative_to(self._base_path)
        except ValueError:  # pragma: no cover - defensive fallback
            markdown_rel = artifact.markdown_path

        record: dict[str, object] = {
            "id": artifact.source.paper_id,
            "title": artifact.source.title,
            "abstract": artifact.source.abstract,
            "summary": artifact.markdown,
            "summary_time": run_at.isoformat(),
            "migrated_at": run_at.isoformat(),
            "source": _SUMMARY_SOURCE_TAG,
            "source_file": str(markdown_rel),
        }
        if artifact.source.score is not None:
            record["score"] = artifact.source.score
        if artifact.source.categories:
            record["categories"] = artifact.source.categories
        if artifact.document.language:
            record["lang"] = artifact.document.language
        return record

    def _build_manifest(
        self,
        *,
        run_id: str,
        run_at: datetime,
        total_sources: int,
        artifacts: Sequence[SummaryArtifact],
        jsonl_path: Path,
        markdown_dir: Path,
    ) -> dict[str, object]:
        return {
            "run_id": run_id,
            "generated_at": run_at.isoformat(),
            "total_sources": total_sources,
            "summarized": len(artifacts),
            "skipped": max(0, total_sources - len(artifacts)),
            "jsonl_path": str(jsonl_path),
            "markdown_dir": str(markdown_dir),
            "pdf_dir": str(self._sources.pdf_dir),
            "llm_alias": self._llm_config.alias,
        }


__all__ = ["SummaryPipeline", "SummaryDataSources"]


def _is_stub_llm(config: LLMConfig) -> bool:
    base_url = config.base_url.strip().lower()
    return base_url.startswith("stub://") or base_url.startswith("http://localhost")
