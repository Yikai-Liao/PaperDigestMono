"""Scheduler configuration models."""

from __future__ import annotations

from pydantic import Field

from papersys.config.base import BaseConfig


class SchedulerJobConfig(BaseConfig):
    """Configuration for a single scheduled job."""

    enabled: bool = Field(True, description="Whether the job is active")
    interval_minutes: int = Field(60, ge=1, description="Interval between runs in minutes")
    dry_run: bool = Field(True, description="Run in dry mode without side effects")
    max_instances: int = Field(1, ge=1, description="Maximum concurrent job instances")


class SchedulerConfig(BaseConfig):
    """Scheduler-wide configuration aggregating multiple jobs."""

    timezone: str = Field("UTC", description="Timezone used by the scheduler")
    summary: SchedulerJobConfig | None = Field(None, description="Summary pipeline schedule")
    recommendation: SchedulerJobConfig | None = Field(None, description="Recommendation pipeline schedule")


__all__ = ["SchedulerJobConfig", "SchedulerConfig"]
