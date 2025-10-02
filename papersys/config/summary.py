"""Summary pipeline configuration models."""

from __future__ import annotations

from pydantic import Field

from papersys.config.base import BaseConfig


class PdfFetchConfig(BaseConfig):
    """Filesystem and network settings for summary artefact acquisition."""

    output_dir: str = Field("./pdfs", description="Directory for downloaded/processed PDFs")
    delay: int = Field(3, ge=0, description="Delay in seconds between requests")
    max_retry: int = Field(3, ge=1, description="Maximum retry attempts for failed operations")
    fetch_latex_source: bool = Field(False, description="Download arXiv LaTeX source for summarization context")


class SummaryLLMConfig(BaseConfig):
    """Behavioural controls for the summarisation language model."""

    model: str = Field(..., description="LLM alias to use for summarisation")
    language: str = Field("en", description="Target language for summaries")
    enable_latex: bool = Field(False, description="Allow the LLM to emit LaTeX expressions in output")


class SummaryPipelineConfig(BaseConfig):
    """Complete summary pipeline configuration."""

    pdf: PdfFetchConfig
    llm: SummaryLLMConfig


__all__ = ["PdfFetchConfig", "SummaryLLMConfig", "SummaryPipelineConfig"]
