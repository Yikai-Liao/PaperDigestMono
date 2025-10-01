"""High-level orchestration for the summary pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from loguru import logger

from papersys.config import AppConfig, SummaryPipelineConfig
from papersys.config.llm import LLMConfig

from .generator import SummaryGenerator
from .models import SummaryArtifact, SummarySource
from .pdf import PdfFetcher
from .renderer import SummaryRenderer


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


class SummaryPipeline:
    """Convenience wrapper that wires together PDF fetching, LLM summarisation and rendering."""

    def __init__(self, config: AppConfig, *, base_path: Path | None = None, template: str | None = None) -> None:
        if config.summary_pipeline is None:
            raise ValueError("summary_pipeline config is required for summary operations")
        self._config = config
        self._pipeline_cfg: SummaryPipelineConfig = config.summary_pipeline
        self._base_path = base_path or config.data_root or Path.cwd()
        self._sources = self._resolve_sources()
        self._renderer = SummaryRenderer(template=template)

        llm_config = self._resolve_llm_config(self._pipeline_cfg.pdf.model)
        self._generator = SummaryGenerator(llm_config, default_language=self._pipeline_cfg.pdf.language)
        self._fetcher = PdfFetcher(
            self._sources.pdf_dir,
            delay=self._pipeline_cfg.pdf.delay,
            max_retry=self._pipeline_cfg.pdf.max_retry,
        )

    def _resolve_sources(self) -> SummaryDataSources:
        pdf_dir = self._resolve_path(self._pipeline_cfg.pdf.output_dir)
        markdown_dir = pdf_dir / "markdown"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        return SummaryDataSources(pdf_dir=pdf_dir, markdown_dir=markdown_dir)

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

    # ------------------------------------------------------------------
    def describe_sources(self) -> SummaryDataSources:
        """Return the resolved data sources without mutating state."""
        return SummaryDataSources(
            pdf_dir=self._sources.pdf_dir,
            markdown_dir=self._sources.markdown_dir,
        )

    def run(self, sources: Iterable[SummarySource], *, dry_run: bool = False) -> list[SummaryArtifact]:
        self._sources.ensure_directories()
        if dry_run:
            logger.info(
                "Summary pipeline dry-run completed. PDF dir={}, markdown dir={}",
                self._sources.pdf_dir,
                self._sources.markdown_dir,
            )
            return []

        artifacts: list[SummaryArtifact] = []
        for source in sources:
            pdf_path = self._fetcher.fetch(source)
            document = self._generator.generate(source)
            markdown = self._renderer.render(document)
            markdown_path = self._sources.markdown_dir / f"{source.paper_id}.md"
            markdown_path.write_text(markdown, encoding="utf-8")
            artifacts.append(
                SummaryArtifact(
                    source=source,
                    pdf_path=pdf_path,
                    markdown_path=markdown_path,
                    document=document,
                    markdown=markdown,
                )
            )
            logger.info(
                "Summary generated for {} | pdf={} | markdown={}",
                source.paper_id,
                pdf_path.name,
                markdown_path.name,
            )
        return artifacts


__all__ = ["SummaryPipeline", "SummaryDataSources"]
