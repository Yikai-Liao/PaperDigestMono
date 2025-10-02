"""Configuration models for ingestion (arXiv OAI-PMH/RSS crawling)."""

from __future__ import annotations

from pydantic import Field

from .base import BaseConfig


class IngestionConfig(BaseConfig):
    """Configuration for metadata ingestion from arXiv."""

    enabled: bool = Field(True, description="Whether ingestion is enabled")
    output_dir: str = Field("metadata/raw/arxiv", description="Output directory for raw metadata (CSV)")
    curated_dir: str = Field("metadata/curated", description="Directory for curated metadata")
    
    # Fetch settings
    start_date: str | None = Field(None, description="Start date for incremental fetch (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="End date for incremental fetch (YYYY-MM-DD)")
    batch_size: int = Field(1000, description="Number of records per OAI-PMH request", ge=1)
    max_retries: int = Field(3, description="Max retries for failed requests", ge=0)
    retry_delay: float = Field(5.0, description="Delay between retries (seconds)", ge=0)
    
    # OAI-PMH endpoint
    oai_base_url: str = Field(
        "http://export.arxiv.org/oai2",
        description="arXiv OAI-PMH base URL"
    )
    metadata_prefix: str = Field("arXiv", description="OAI metadata format")
    
    # Filtering
    categories: list[str] = Field(
        default_factory=list,
        description="Filter by arXiv categories (empty = all)"
    )
    
    # Debug options
    save_raw_responses: bool = Field(
        False,
        description="Save original OAI responses to debug/ (for troubleshooting only)"
    )


__all__ = ["IngestionConfig"]
