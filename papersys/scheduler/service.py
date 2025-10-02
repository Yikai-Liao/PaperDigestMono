from datetime import datetime
from typing import Any, Callable, Dict, Tuple
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from papersys.backup import BackupService
from papersys.config import AppConfig, SchedulerJobConfig


class SchedulerService:
    """Manages scheduled jobs for the paper processing pipeline."""

    def __init__(self, config: AppConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        timezone = (config.scheduler.timezone if config.scheduler and config.scheduler.timezone else "UTC")
        self.scheduler = BackgroundScheduler(timezone=timezone)
        self._timezone = timezone
        self._jobs: Dict[str, Tuple[Callable[[SchedulerJobConfig], None], SchedulerJobConfig]] = {}

    def setup_jobs(self):
        """Registers jobs based on the application configuration."""
        if not self.config.scheduler or not self.config.scheduler.enabled:
            logger.warning("Scheduler is disabled in the configuration. No jobs will be scheduled.")
            return

        self.scheduler.remove_all_jobs()
        self._jobs.clear()

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

        if self.config.scheduler.backup_job:
            self._register_job(
                job_id="backup",
                job_config=self.config.scheduler.backup_job,
                func=self._run_backup_pipeline,
            )

        if self.dry_run:
            logger.info("[Dry Run] Jobs have been validated and registered. Scheduler will not be started.")
            for job in self.scheduler.get_jobs():
                logger.info(f"[Dry Run] Job '{job.id}' with trigger: {job.trigger}")
            return

    def _register_job(self, job_id: str, job_config: SchedulerJobConfig, func: Callable[[SchedulerJobConfig], None]):
        """Helper to register a single job."""
        if not job_config.enabled:
            logger.info(f"Job '{job_id}' is disabled, skipping.")
            return

        logger.info(f"Registering job '{job_id}' with cron schedule: '{job_config.cron}'")
        trigger = CronTrigger.from_crontab(job_config.cron, timezone=self._timezone)
        self.scheduler.add_job(
            func,
            trigger,
            id=job_id,
            name=job_config.name,
            kwargs={"job_config": job_config},
            replace_existing=True,
        )
        self._jobs[job_id] = (func, job_config)

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

    def _run_backup_pipeline(self, job_config: SchedulerJobConfig):
        """Execute the backup pipeline using the backup service."""
        logger.info(f"Executing backup pipeline for job '{job_config.name}'...")
        service = BackupService(self.config, dry_run=self.dry_run)
        result = service.run()
        if result is None:
            logger.info("Backup configuration disabled or missing; nothing to do.")
        else:
            logger.info(
                "Backup completed with %s files uploaded.",
                result.file_count,
            )

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
        return [
            {"id": job.id, "name": job.name, "trigger": str(job.trigger)}
            for job in self.scheduler.get_jobs()
        ]

    def trigger_job(self, job_id: str) -> bool:
        """Trigger a registered job to run immediately."""
        job_entry = self._jobs.get(job_id)
        job = self.scheduler.get_job(job_id)
        if job_entry is None or job is None:
            return False

        func, job_config = job_entry

        if self.dry_run:
            logger.info("[Dry Run] Manual trigger for job '{}' skipped.", job_id)
            return True

        logger.info("Manually triggering job '{}'", job_id)
        run_date = datetime.now(self.scheduler.timezone)
        self.scheduler.add_job(
            func,
            trigger="date",
            run_date=run_date,
            kwargs={"job_config": job_config},
            id=f"{job_id}-manual-{uuid4().hex}",
        )
        if self.scheduler.running:
            self.scheduler.wakeup()
        return True