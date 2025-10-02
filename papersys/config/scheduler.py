"""Scheduler configuration models."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from papersys.config.base import BaseConfig


class SchedulerJobConfig(BaseConfig):
    """Configuration for a single scheduled job."""

    enabled: bool = Field(True, description="Whether the job is active")
    name: str = Field(..., description="Human-friendly name for the job")
    cron: str = Field(
        ...,
        description="Cron expression (minute hour day month weekday)",
        validation_alias=AliasChoices("cron", "cron_schedule"),
        serialization_alias="cron",
    )


class SchedulerConfig(BaseConfig):
    """Scheduler-wide configuration aggregating multiple jobs."""

    enabled: bool = Field(True, description="Whether the scheduler is active")
    timezone: str = Field("UTC", description="Timezone used by the scheduler")
    ingest_job: SchedulerJobConfig | None = Field(None, description="Ingestion job schedule")
    embed_job: SchedulerJobConfig | None = Field(None, description="Embedding generation job schedule")
    embedding_backfill_job: SchedulerJobConfig | None = Field(None, description="Embedding backfill job schedule")
    recommend_job: SchedulerJobConfig | None = Field(None, description="Recommendation pipeline job schedule")
    summary_job: SchedulerJobConfig | None = Field(None, description="Summary pipeline job schedule")
    backup_job: SchedulerJobConfig | None = Field(None, description="Backup pipeline job schedule")


__all__ = ["SchedulerJobConfig", "SchedulerConfig"]