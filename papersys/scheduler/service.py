from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Dict, Tuple
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from papersys.config import AppConfig, SchedulerJobConfig


@dataclass(slots=True)
class JobMetrics:
    """Holds execution statistics for a scheduler job."""

    job_id: str
    job_name: str
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    dry_run_count: int = 0
    last_status: str | None = None
    last_error: str | None = None
    last_start_time: datetime | None = None
    last_end_time: datetime | None = None
    last_duration_seconds: float | None = None
    next_run_time: datetime | None = None


class SchedulerMetricsRegistry:
    """Thread-safe metrics collector for scheduler jobs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._metrics: dict[str, JobMetrics] = {}

    def ensure_job(self, job_id: str, job_name: str) -> JobMetrics:
        with self._lock:
            metrics = self._metrics.get(job_id)
            if metrics is None:
                metrics = JobMetrics(job_id=job_id, job_name=job_name)
                self._metrics[job_id] = metrics
            else:
                metrics.job_name = job_name
            return metrics

    def record_start(self, job_id: str, job_name: str, start_time: datetime) -> None:
        self.ensure_job(job_id, job_name)
        with self._lock:
            metrics = self._metrics[job_id]
            metrics.last_start_time = start_time
            metrics.last_status = "running"
            metrics.last_error = None

    def record_success(
        self,
        job_id: str,
        job_name: str,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
    ) -> None:
        self.ensure_job(job_id, job_name)
        with self._lock:
            metrics = self._metrics[job_id]
            metrics.total_runs += 1
            metrics.success_count += 1
            metrics.last_status = "success"
            metrics.last_start_time = start_time
            metrics.last_end_time = end_time
            metrics.last_duration_seconds = duration_seconds

    def record_failure(
        self,
        job_id: str,
        job_name: str,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        error: str,
    ) -> None:
        self.ensure_job(job_id, job_name)
        with self._lock:
            metrics = self._metrics[job_id]
            metrics.total_runs += 1
            metrics.failure_count += 1
            metrics.last_status = "failure"
            metrics.last_error = error
            metrics.last_start_time = start_time
            metrics.last_end_time = end_time
            metrics.last_duration_seconds = duration_seconds

    def record_dry_run(self, job_id: str, job_name: str, timestamp: datetime) -> None:
        self.ensure_job(job_id, job_name)
        with self._lock:
            metrics = self._metrics[job_id]
            metrics.total_runs += 1
            metrics.dry_run_count += 1
            metrics.last_status = "dry_run"
            metrics.last_start_time = timestamp
            metrics.last_end_time = timestamp
            metrics.last_duration_seconds = 0.0

    def set_next_run(self, job_id: str, job_name: str, next_run: datetime | None) -> None:
        self.ensure_job(job_id, job_name)
        with self._lock:
            metrics = self._metrics[job_id]
            metrics.next_run_time = next_run

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {job_id: asdict(metrics) for job_id, metrics in self._metrics.items()}

    def export_prometheus(self) -> str:
        with self._lock:
            metrics_values = list(self._metrics.values())

        lines: list[str] = []
        lines.append(
            "# HELP scheduler_job_runs_total Total number of scheduler job executions (success, failure, dry-run)."
        )
        lines.append("# TYPE scheduler_job_runs_total counter")
        for metrics in metrics_values:
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(f"scheduler_job_runs_total{{{labels}}} {metrics.total_runs}")

        lines.append("# HELP scheduler_job_success_total Number of successful scheduler job executions.")
        lines.append("# TYPE scheduler_job_success_total counter")
        for metrics in metrics_values:
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(f"scheduler_job_success_total{{{labels}}} {metrics.success_count}")

        lines.append("# HELP scheduler_job_failure_total Number of failed scheduler job executions.")
        lines.append("# TYPE scheduler_job_failure_total counter")
        for metrics in metrics_values:
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(f"scheduler_job_failure_total{{{labels}}} {metrics.failure_count}")

        lines.append("# HELP scheduler_job_dry_run_total Number of dry-run scheduler job simulations.")
        lines.append("# TYPE scheduler_job_dry_run_total counter")
        for metrics in metrics_values:
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(f"scheduler_job_dry_run_total{{{labels}}} {metrics.dry_run_count}")

        lines.append("# HELP scheduler_job_last_duration_seconds Duration of the last job execution in seconds.")
        lines.append("# TYPE scheduler_job_last_duration_seconds gauge")
        for metrics in metrics_values:
            if metrics.last_duration_seconds is None:
                continue
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(
                f"scheduler_job_last_duration_seconds{{{labels}}} {metrics.last_duration_seconds}"
            )

        lines.append("# HELP scheduler_job_last_end_timestamp_seconds End timestamp of the last job execution (epoch seconds).")
        lines.append("# TYPE scheduler_job_last_end_timestamp_seconds gauge")
        for metrics in metrics_values:
            if metrics.last_end_time is None:
                continue
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(
                f"scheduler_job_last_end_timestamp_seconds{{{labels}}} {metrics.last_end_time.timestamp()}"
            )

        lines.append("# HELP scheduler_job_next_run_timestamp_seconds Timestamp of the next scheduled run (epoch seconds).")
        lines.append("# TYPE scheduler_job_next_run_timestamp_seconds gauge")
        for metrics in metrics_values:
            if metrics.next_run_time is None:
                continue
            labels = f'job_id="{metrics.job_id}",job_name="{metrics.job_name}"'
            lines.append(
                f"scheduler_job_next_run_timestamp_seconds{{{labels}}} {metrics.next_run_time.timestamp()}"
            )

        return "\n".join(lines) + "\n"


class SchedulerService:
    """Manages scheduled jobs for the paper processing pipeline."""

    def __init__(self, config: AppConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        timezone = (config.scheduler.timezone if config.scheduler and config.scheduler.timezone else "UTC")
        self.scheduler = BackgroundScheduler(timezone=timezone)
        self._timezone = timezone
        self._jobs: Dict[str, Tuple[Callable[[SchedulerJobConfig], None], SchedulerJobConfig]] = {}
        self._job_runners: dict[str, Callable[[], None]] = {}
        self.metrics = SchedulerMetricsRegistry()
        self._file_sink_id: int | None = None
        self._setup_logging_sink()

    def _setup_logging_sink(self) -> None:
        """Ensure scheduler logs are persisted to a rotating file sink."""

        log_dir = Path("logs")
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            sink_path = log_dir / "scheduler.log"
            self._file_sink_id = logger.add(
                sink_path,
                rotation="5 MB",
                retention=5,
                enqueue=True,
                serialize=True,
                level="INFO",
            )
        except Exception as exc:  # pragma: no cover - filesystem issues are environment-specific
            logger.warning("Failed to initialise scheduler file log sink: {}", exc)
            self._file_sink_id = None

    def setup_jobs(self):
        """Registers jobs based on the application configuration."""
        if not self.config.scheduler or not self.config.scheduler.enabled:
            logger.warning("Scheduler is disabled in the configuration. No jobs will be scheduled.")
            return

        self.scheduler.remove_all_jobs()
        self._jobs.clear()
        self._job_runners.clear()

        logger.info("Setting up scheduled jobs...")
        logger.info("Scheduler timezone: {}", self._timezone)
        if self.config.scheduler.recommend_job:
            self._register_job(
                job_id="recommend",
                job_config=self.config.scheduler.recommend_job,
                func=self._run_recommend_pipeline,
            )

        if self.config.scheduler.summary_job:
            self._register_job(
                job_id="summary",
                job_config=self.config.scheduler.summary_job,
                func=self._run_summary_pipeline,
            )

        if self.dry_run:
            logger.info("[Dry Run] Jobs have been validated and registered. Scheduler will not be started.")
            for job in self.scheduler.get_jobs():
                logger.info(f"[Dry Run] Job '{job.id}' with trigger: {job.trigger}")
                self.metrics.record_dry_run(job.id, job.name or job.id, datetime.now(self.scheduler.timezone))
            return

    def _register_job(self, job_id: str, job_config: SchedulerJobConfig, func: Callable[[SchedulerJobConfig], None]):
        """Helper to register a single job."""
        if not job_config.enabled:
            logger.info(f"Job '{job_id}' is disabled, skipping.")
            return

        logger.info(f"Registering job '{job_id}' with cron schedule: '{job_config.cron}'")
        trigger = CronTrigger.from_crontab(job_config.cron, timezone=self._timezone)
        runner = self._build_job_runner(job_id, job_config, func)
        self.scheduler.add_job(
            runner,
            trigger,
            id=job_id,
            name=job_config.name,
            replace_existing=True,
        )
        self._jobs[job_id] = (func, job_config)
        self._job_runners[job_id] = runner
        self.metrics.ensure_job(job_id, job_config.name)
        job = self.scheduler.get_job(job_id)
        next_run = self._job_next_run(job) if job is not None else None
        self.metrics.set_next_run(job_id, job_config.name, next_run)

    def _run_recommend_pipeline(self, job_config: SchedulerJobConfig):
        """Placeholder for the actual recommendation pipeline execution."""
        logger.info(f"Executing recommendation pipeline for job '{job_config.name}'...")
        # In a real implementation, this would trigger the recommendation pipeline
        # from papersys.recommend.pipeline
        logger.info("Recommendation pipeline job finished.")

    def _run_summary_pipeline(self, job_config: SchedulerJobConfig):
        """Placeholder for the actual summary pipeline execution."""
        logger.info(f"Executing summary pipeline for job '{job_config.name}'...")
        # In a real implementation, this would trigger the summary pipeline
        # from papersys.summary.pipeline
        logger.info("Summary pipeline job finished.")

    def start(self):
        """Starts the scheduler if not in dry run mode."""
        if self.dry_run:
            logger.info("[Dry Run] Scheduler start is skipped.")
            return
        if not self.scheduler.get_jobs():
            logger.warning("No jobs are scheduled. The scheduler will not start.")
            return

        if self.scheduler.running:
            logger.info("Scheduler is already running.")
            return

        logger.info("Starting scheduler...")
        self.scheduler.start()

    def shutdown(self):
        """Shuts down the scheduler gracefully."""
        if self.scheduler.running:
            logger.info("Shutting down scheduler...")
            self.scheduler.shutdown()
            logger.info("Scheduler has been shut down.")
        else:
            logger.info("Scheduler is not running.")

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return current scheduled jobs in serialisable form."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = self._job_next_run(job)
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "trigger": str(job.trigger),
                    "next_run_time": next_run.isoformat() if next_run else None,
                }
            )
        return jobs

    def trigger_job(self, job_id: str) -> bool:
        """Trigger a registered job to run immediately."""
        job_entry = self._jobs.get(job_id)
        job = self.scheduler.get_job(job_id)
        if job_entry is None or job is None:
            return False

        func, job_config = job_entry

        if self.dry_run:
            logger.info("[Dry Run] Manual trigger for job '{}' skipped.", job_id)
            self.metrics.record_dry_run(job_id, job_config.name, datetime.now(self.scheduler.timezone))
            return True

        logger.info("Manually triggering job '{}'", job_id)
        run_date = datetime.now(self.scheduler.timezone)
        runner = self._job_runners.get(job_id)
        if runner is None:
            runner = self._build_job_runner(job_id, job_config, func)
            self._job_runners[job_id] = runner
        self.scheduler.add_job(
            runner,
            trigger="date",
            run_date=run_date,
            id=f"{job_id}-manual-{uuid4().hex}",
        )
        if self.scheduler.running:
            self.scheduler.wakeup()
        return True

    def get_metrics_snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a serialisable snapshot of the current metrics."""

        return self.metrics.snapshot()

    def export_metrics(self) -> str:
        """Return Prometheus-formatted metrics."""

        return self.metrics.export_prometheus()

    def _build_job_runner(
        self,
        job_id: str,
        job_config: SchedulerJobConfig,
        func: Callable[[SchedulerJobConfig], None],
    ) -> Callable[[], None]:
        def _runner() -> None:
            self._execute_job(job_id, job_config, func)

        return _runner

    def _execute_job(
        self,
        job_id: str,
        job_config: SchedulerJobConfig,
        func: Callable[[SchedulerJobConfig], None],
    ) -> None:
        run_id = uuid4().hex
        bound_logger = logger.bind(job_id=job_id, job_name=job_config.name, run_id=run_id)
        start_time = datetime.now(self.scheduler.timezone)
        self.metrics.record_start(job_id, job_config.name, start_time)

        bound_logger.info("Job execution started", dry_run=self.dry_run, timezone=str(self._timezone))

        if self.dry_run:
            bound_logger.info("Dry-run mode active; skipping execution")
            self.metrics.record_dry_run(job_id, job_config.name, start_time)
            return

        timer_start = perf_counter()
        try:
            func(job_config)
        except Exception as exc:
            duration = perf_counter() - timer_start
            end_time = datetime.now(self.scheduler.timezone)
            error_message = str(exc)
            self.metrics.record_failure(
                job_id,
                job_config.name,
                start_time,
                end_time,
                duration,
                error_message,
            )
            self.metrics.set_next_run(
                job_id,
                job_config.name,
                self._next_run_time(job_id),
            )
            bound_logger.error(
                "Job execution failed",
                duration_seconds=duration,
                error=error_message,
            )
            raise

        duration = perf_counter() - timer_start
        end_time = datetime.now(self.scheduler.timezone)
        self.metrics.record_success(job_id, job_config.name, start_time, end_time, duration)
        self.metrics.set_next_run(job_id, job_config.name, self._next_run_time(job_id))
        bound_logger.info("Job execution finished", status="success", duration_seconds=duration)

    def _next_run_time(self, job_id: str) -> datetime | None:
        job = self.scheduler.get_job(job_id)
        if job is None:
            return None
        return self._job_next_run(job)

    @staticmethod
    def _job_next_run(job: Any) -> datetime | None:
        try:
            return job.next_run_time
        except AttributeError:
            return None

    def shutdown(self):
        """Shuts down the scheduler gracefully."""
        if self.scheduler.running:
            logger.info("Shutting down scheduler...")
            self.scheduler.shutdown()
            logger.info("Scheduler has been shut down.")
        else:
            logger.info("Scheduler is not running.")

        if self._file_sink_id is not None:
            logger.remove(self._file_sink_id)
            self._file_sink_id = None