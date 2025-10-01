"""Scheduler configuration models."""

from __future__ import annotations

from pydantic import Field

from papersys.config.base import BaseConfig


class SchedulerJobConfig(BaseConfig):
    """Configuration for a single scheduled job."""

    enabled: bool = Field(True, description="Whether the job is active")
    name: str = Field(..., description="The name of the job")
    cron_schedule: str = Field(..., description="Cron-style schedule for the job")


class SchedulerConfig(BaseConfig):
    """Scheduler-wide configuration aggregating multiple jobs."""

    enabled: bool = Field(True, description="Whether the scheduler is active")
    recommend_job: SchedulerJobConfig | None = Field(None, description="Recommendation pipeline job schedule")
    summary_job: SchedulerJobConfig | None = Field(None, description="Summary pipeline job schedule")


__all__ = ["SchedulerJobConfig", "SchedulerConfig"]