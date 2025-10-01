"""Summary pipeline configuration models."""

from __future__ import annotations

from pydantic import Field

from papersys.config.base import BaseConfig


class PdfConfig(BaseConfig):
    """Configuration for PDF processing in summary pipeline."""

    output_dir: str = Field("./pdfs", description="Directory for downloaded/processed PDFs")
    delay: int = Field(3, ge=0, description="Delay in seconds between requests")
    max_retry: int = Field(3, ge=1, description="Maximum retry attempts for failed operations")
    model: str = Field(..., description="LLM alias to use for summarization")
    language: str = Field("en", description="Target language for summaries")
    enable_latex: bool = Field(False, description="Whether to enable LaTeX rendering in output")
    acceptable_cache_model: list[str] = Field(
        default_factory=lambda: ["gemini-2.5*", "deepseek*", "grok-3*"],
        description="Model patterns acceptable for cache reuse (supports wildcards)",
    )


class SummaryPipelineConfig(BaseConfig):
    """Complete summary pipeline configuration."""

    pdf: PdfConfig


__all__ = ["PdfConfig", "SummaryPipelineConfig"]
